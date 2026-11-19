"""Modèle de données du service d'authentification (base auth_db)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, LargeBinary, String, Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from scolaris_common.audit import modele_boite_envoi
from scolaris_common.types import HorodatageUTC


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


ROLES = ("ETUDIANT", "ENSEIGNANT", "ADMINISTRATEUR")
STATUTS = ("EN_ATTENTE_ACTIVATION", "ACTIF", "VERROUILLE", "DESACTIVE")


class Utilisateur(Base):
    __tablename__ = "utilisateur"
    __table_args__ = (
        CheckConstraint(f"role IN {ROLES}", name="ck_utilisateur_role"),
        CheckConstraint(f"statut IN {STATUTS}", name="ck_utilisateur_statut"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    identifiant: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    nom: Mapped[str | None] = mapped_column(String(60))
    prenom: Mapped[str | None] = mapped_column(String(60))
    hash_mot_de_passe: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    statut: Mapped[str] = mapped_column(String(25), default="EN_ATTENTE_ACTIVATION")
    # Secret TOTP chiffré en AES-256-GCM ; jamais stocké en clair.
    secret_mfa_chiffre: Mapped[bytes | None] = mapped_column(LargeBinary)
    secret_mfa_en_attente: Mapped[bytes | None] = mapped_column(LargeBinary)
    mfa_dernier_pas: Mapped[int | None] = mapped_column(Integer)  # anti-rejeu du code TOTP
    tentatives_echouees: Mapped[int] = mapped_column(Integer, default=0)
    verrouille_jusqua: Mapped[datetime | None] = mapped_column(HorodatageUTC)
    # Lien vers la fiche du service Étudiants, inscrit dans le jeton (claim « etu »).
    etudiant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    cree_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)
    cree_par: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    derniere_connexion: Mapped[datetime | None] = mapped_column(HorodatageUTC)


class JetonRafraichissement(Base):
    __tablename__ = "jeton_rafraichissement"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    utilisateur_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilisateur.id"), index=True)
    famille: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    debut_famille: Mapped[datetime] = mapped_column(HorodatageUTC)
    empreinte: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256, jamais le jeton
    expire_le: Mapped[datetime] = mapped_column(HorodatageUTC)
    utilise: Mapped[bool] = mapped_column(Boolean, default=False)
    revoque: Mapped[bool] = mapped_column(Boolean, default=False)

    utilisateur: Mapped[Utilisateur] = relationship()


class JetonActivation(Base):
    __tablename__ = "jeton_activation"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    utilisateur_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilisateur.id"), index=True)
    empreinte: Mapped[str] = mapped_column(String(64), unique=True)
    expire_le: Mapped[datetime] = mapped_column(HorodatageUTC)
    utilise: Mapped[bool] = mapped_column(Boolean, default=False)

    utilisateur: Mapped[Utilisateur] = relationship()


class Revocation(Base):
    """Révocation de toutes les sessions d'un compte, diffusée aux autres services."""
    __tablename__ = "revocation"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    utilisateur_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    instant_ms: Mapped[int] = mapped_column(BigInteger, index=True)


EvenementSortant = modele_boite_envoi(Base)


class SessionOuverte(Base):
    """F27 Espace sécurité : une session par famille de jetons de rafraîchissement (un appareil)."""
    __tablename__ = "session_ouverte"

    famille: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    utilisateur_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilisateur.id"), index=True)
    ouverte_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)
    derniere_activite: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)
    adresse_ip: Mapped[str | None] = mapped_column(String(45))
    # Description courte (« Edge sous Windows ») : la chaîne User-Agent brute n'est pas conservée.
    appareil: Mapped[str] = mapped_column(String(80))
    fermee: Mapped[bool] = mapped_column(Boolean, default=False)


class HistoriqueConnexion(Base):
    """Connexions réussies, échouées et verrouillages, consultables par le titulaire du compte."""
    __tablename__ = "historique_connexion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    utilisateur_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilisateur.id"), index=True)
    horodatage: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant, index=True)
    resultat: Mapped[str] = mapped_column(String(12))
    adresse_ip: Mapped[str | None] = mapped_column(String(45))
    appareil: Mapped[str] = mapped_column(String(80))
