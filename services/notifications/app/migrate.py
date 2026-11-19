"""Création du schéma notifications_db avec le compte de migration (droits DDL)."""
from scolaris_common import logs
from scolaris_common.config import lire_secret
from scolaris_common.db import Bdd

from .models import Base

if __name__ == "__main__":
    log = logs.configurer("notifications.migration")
    Base.metadata.create_all(Bdd(lire_secret("notifications_db_url_migration")).moteur)
    log.info("Schéma notifications_db à jour.")
