"""Modèle de données du service Notes (base notes_db)."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from scolaris_common.audit import modele_boite_envoi
from scolaris_common.calendrier import annee_academique  # noqa: F401  (réexporté)
from scolaris_common.types import HorodatageUTC

TYPES_EVALUATION = ("CONTROLE_CONTINU", "EXAMEN", "TP", "RATTRAPAGE")


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Semestre(Base):
    """Semestre d'une année académique ; porte la fenêtre de saisie ouverte par l'administrateur (F17)."""
    __tablename__ = "semestre"
    __table_args__ = (
        UniqueConstraint("annee_academique", "numero", name="uq_semestre"),
        CheckConstraint("numero IN (1, 2)", name="ck_semestre_numero"),
        CheckConstraint("saisie_fin IS NULL OR saisie_debut IS NULL OR saisie_fin >= saisie_debut", name="ck_semestre_fenetre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    annee_academique: Mapped[str] = mapped_column(String(9), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    saisie_debut: Mapped[date | None] = mapped_column(Date)
    saisie_fin: Mapped[date | None] = mapped_column(Date)

    @property
    def libelle(self) -> str:
        return f"Semestre {self.numero} – {self.annee_academique}"

    def saisie_ouverte(self, jour: date | None = None) -> bool:
        jour = jour or date.today()
        return self.saisie_debut is not None and self.saisie_fin is not None and self.saisie_debut <= jour <= self.saisie_fin


class Matiere(Base):
    __tablename__ = "matiere"
    __table_args__ = (CheckConstraint("coefficient >= 0.5 AND coefficient <= 10", name="ck_matiere_coef"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    libelle: Mapped[str] = mapped_column(String(80))
    coefficient: Mapped[Decimal] = mapped_column(Numeric(3, 1))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Rattachement pédagogique : la classe vit dans le service Étudiants (référence par identifiant).
    classe_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    semestre_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("semestre.id", ondelete="RESTRICT"), index=True)
    # Publication (F18) : tant qu'elle est nulle, les notes restent invisibles pour les étudiants.
    publiee_le: Mapped[datetime | None] = mapped_column(HorodatageUTC)
    publiee_par: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    affectations: Mapped[list["Affectation"]] = relationship(back_populates="matiere")
    semestre: Mapped[Semestre | None] = relationship()


class Affectation(Base):
    """Lien enseignant – matière pour une année : borne les droits de saisie (R16)."""
    __tablename__ = "affectation"
    __table_args__ = (UniqueConstraint("enseignant_id", "matiere_id", "annee_academique", name="uq_affectation"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    enseignant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    matiere_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matiere.id", ondelete="RESTRICT"))
    annee_academique: Mapped[str] = mapped_column(String(9))
    cree_par: Mapped[uuid.UUID] = mapped_column(Uuid)
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)

    matiere: Mapped[Matiere] = relationship(back_populates="affectations")


class Note(Base):
    __tablename__ = "note"
    __table_args__ = (
        CheckConstraint("valeur >= 0 AND valeur <= 20", name="ck_note_valeur"),
        CheckConstraint(f"type_evaluation IN {TYPES_EVALUATION}", name="ck_note_type"),
        # Une même évaluation ne peut pas être saisie deux fois.
        UniqueConstraint("etudiant_id", "matiere_id", "type_evaluation", "date_evaluation", name="uq_note_evaluation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    etudiant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    # RESTRICT : une matière portant des notes ne peut pas être supprimée (R14).
    matiere_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matiere.id", ondelete="RESTRICT"), index=True)
    valeur: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    type_evaluation: Mapped[str] = mapped_column(String(20))
    date_evaluation: Mapped[date] = mapped_column(Date)
    saisie_par: Mapped[uuid.UUID] = mapped_column(Uuid)
    saisie_par_identifiant: Mapped[str] = mapped_column(String(80))
    saisie_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)
    modifie_le: Mapped[datetime | None] = mapped_column(HorodatageUTC)
    version: Mapped[int] = mapped_column(Integer, default=1)

    matiere: Mapped[Matiere] = relationship()
    historique: Mapped[list["HistoriqueNote"]] = relationship(back_populates="note", order_by="HistoriqueNote.modifie_le")

    __mapper_args__ = {"version_id_col": version}


class HistoriqueNote(Base):
    """Historique en ajout seul : le compte applicatif n'a ni UPDATE ni DELETE sur cette table."""
    __tablename__ = "historique_note"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("note.id", ondelete="RESTRICT"), index=True)
    ancienne_valeur: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    nouvelle_valeur: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    motif: Mapped[str] = mapped_column(String(255))
    modifie_par: Mapped[uuid.UUID] = mapped_column(Uuid)
    modifie_par_identifiant: Mapped[str] = mapped_column(String(80))
    modifie_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)

    note: Mapped[Note] = relationship(back_populates="historique")


STATUTS_RECLAMATION = ("SOUMISE", "EN_COURS", "ACCEPTEE", "REJETEE")


class Reclamation(Base):
    """F19 : contestation d'une note publiée par l'étudiant, traitée par l'enseignant de la matière."""
    __tablename__ = "reclamation"
    __table_args__ = (CheckConstraint(f"statut IN {STATUTS_RECLAMATION}", name="ck_reclamation_statut"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("note.id", ondelete="RESTRICT"), index=True)
    etudiant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    motif: Mapped[str] = mapped_column(String(500))
    statut: Mapped[str] = mapped_column(String(10), default="SOUMISE")
    reponse: Mapped[str | None] = mapped_column(String(500))
    traitee_par: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    traitee_par_identifiant: Mapped[str | None] = mapped_column(String(80))
    soumise_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)
    traitee_le: Mapped[datetime | None] = mapped_column(HorodatageUTC)
    version: Mapped[int] = mapped_column(Integer, default=1)

    note: Mapped[Note] = relationship()

    __mapper_args__ = {"version_id_col": version}


class ReleveEmis(Base):
    """F20 : chaque relevé PDF reçoit un code de vérification ; seule son empreinte est conservée."""
    __tablename__ = "releve_emis"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    etudiant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    matricule: Mapped[str] = mapped_column(String(14))
    annee_academique: Mapped[str] = mapped_column(String(9))
    moyenne_generale: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    empreinte: Mapped[str] = mapped_column(String(64))
    emis_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)


EvenementSortant = modele_boite_envoi(Base)
