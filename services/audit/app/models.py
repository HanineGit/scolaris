"""Journal d'audit (base audit_db), en ajout seul.

Le compte applicatif n'a que SELECT et INSERT sur ces tables : aucun
événement ne peut être modifié ni supprimé par le service (risque R23).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Integer, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from scolaris_common.types import HorodatageUTC


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EvenementAudit(Base):
    __tablename__ = "evenement_audit"

    numero: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)  # identifiant émis par le service source
    horodatage: Mapped[datetime] = mapped_column(HorodatageUTC, index=True)
    recu_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant)
    service: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(40), index=True)
    resultat: Mapped[str] = mapped_column(String(10), index=True)
    acteur_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    acteur_identifiant: Mapped[str | None] = mapped_column(String(80), index=True)
    role: Mapped[str | None] = mapped_column(String(20))
    ressource: Mapped[str | None] = mapped_column(String(120))
    ressource_id: Mapped[str | None] = mapped_column(String(64))
    adresse_ip: Mapped[str | None] = mapped_column(String(45))
    id_correlation: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    empreinte_precedente: Mapped[str] = mapped_column(String(64))
    empreinte: Mapped[str] = mapped_column(String(64), unique=True)


class VerificationIntegrite(Base):
    __tablename__ = "verification_integrite"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    effectuee_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant, index=True)
    integre: Mapped[bool] = mapped_column(Boolean)
    nombre: Mapped[int] = mapped_column(Integer)
    premier_defaut: Mapped[int | None] = mapped_column(Integer)
