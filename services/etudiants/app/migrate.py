"""Création du schéma etudiant_db avec le compte de migration (droits DDL).

create_all crée les tables manquantes ; les colonnes ajoutées après coup
sont ajoutées par des ordres idempotents (ADD COLUMN IF NOT EXISTS).
"""
from sqlalchemy import text

from scolaris_common import logs
from scolaris_common.config import lire_secret
from scolaris_common.db import Bdd

from .models import Base

EVOLUTIONS = [
    "ALTER TABLE etudiant ADD COLUMN IF NOT EXISTS classe_id uuid REFERENCES classe(id) ON DELETE RESTRICT",
    "CREATE INDEX IF NOT EXISTS ix_etudiant_classe_id ON etudiant (classe_id)",
]

if __name__ == "__main__":
    log = logs.configurer("etudiants.migration")
    moteur = Bdd(lire_secret("etudiant_db_url_migration")).moteur
    Base.metadata.create_all(moteur)
    with moteur.begin() as cx:
        for ordre in EVOLUTIONS:
            cx.execute(text(ordre))
    log.info("Schéma etudiant_db à jour.")
