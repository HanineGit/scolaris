"""Modèle de données du service Étudiants (base etudiant_db)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from scolaris_common.audit import modele_boite_envoi
from scolaris_common.types import HorodatageUTC


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


NIVEAUX = ("L1", "L2", "L3", "M1", "M2")


class Classe(Base):
    """Promotion d'une filière pour une année académique (ex. « L2 Informatique 2026-2027 »)."""
    __tablename__ = "classe"
    __table_args__ = (
        UniqueConstraint("code", "annee_academique", name="uq_classe_annee"),
        CheckConstraint(f"niveau IN {NIVEAUX}", name="ck_classe_niveau"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(12))
    libelle: Mapped[str] = mapped_column(String(80))
    filiere: Mapped[str] = mapped_column(String(60))
    niveau: Mapped[str] = mapped_column(String(2))
    annee_academique: Mapped[str] = mapped_column(String(9), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_par: Mapped[uuid.UUID] = mapped_column(Uuid)
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)


class Etudiant(Base):
    __tablename__ = "etudiant"
    __table_args__ = (CheckConstraint("statut IN ('ACTIF', 'ARCHIVE')", name="ck_etudiant_statut"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    matricule: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(60))
    prenom: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    utilisateur_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    statut: Mapped[str] = mapped_column(String(10), default="ACTIF")
    classe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("classe.id", ondelete="RESTRICT"), index=True)
    cree_par: Mapped[uuid.UUID] = mapped_column(Uuid)
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)
    modifie_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)
    # Verrouillage optimiste : une modification sur une version périmée est refusée (409).
    version: Mapped[int] = mapped_column(Integer, default=1)

    classe: Mapped[Classe | None] = relationship()

    __mapper_args__ = {"version_id_col": version}


EvenementSortant = modele_boite_envoi(Base)
