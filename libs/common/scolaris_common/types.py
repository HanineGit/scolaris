"""Types de colonnes partagés."""
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class HorodatageUTC(TypeDecorator):
    """Date-heure toujours en UTC et toujours avec fuseau, quelle que soit la base.

    Les comparaisons d'expiration (jetons, verrouillage) ne peuvent ainsi jamais
    échouer à cause d'une date sans fuseau.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, valeur: datetime | None, dialect):
        if valeur is None:
            return None
        if valeur.tzinfo is None:
            raise ValueError("Date sans fuseau horaire refusée.")
        return valeur.astimezone(timezone.utc)

    def process_result_value(self, valeur: datetime | None, dialect):
        if valeur is None:
            return None
        return valeur.replace(tzinfo=timezone.utc) if valeur.tzinfo is None else valeur.astimezone(timezone.utc)
