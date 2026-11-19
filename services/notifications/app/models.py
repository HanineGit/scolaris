"""Modèle de données du service Notifications (base notifications_db)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from scolaris_common.types import HorodatageUTC


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Notification(Base):
    """Une ligne par destinataire ; le destinataire est un compte ou une fiche étudiant."""
    __tablename__ = "notification"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    utilisateur_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    etudiant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    categorie: Mapped[str] = mapped_column(String(12))
    titre: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(300))
    lien: Mapped[str | None] = mapped_column(String(120))
    creee_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant, index=True)
    lue_le: Mapped[datetime | None] = mapped_column(HorodatageUTC)
