"""Création du schéma notes_db avec le compte de migration (droits DDL).

Après création, les droits fins sont posés :
- l'historique des notes est en ajout seul (pas d'UPDATE) ;
- seul le retrait d'une affectation utilise DELETE ;
- le compte de lecture ne voit que les tables nécessaires à la consultation mobile.
"""
from sqlalchemy import text

from scolaris_common import logs
from scolaris_common.config import lire_secret
from scolaris_common.db import Bdd

from .models import Base

# Colonnes ajoutées après la création initiale (ordres idempotents).
EVOLUTIONS = [
    "ALTER TABLE matiere ADD COLUMN IF NOT EXISTS classe_id uuid",
    "ALTER TABLE matiere ADD COLUMN IF NOT EXISTS semestre_id uuid REFERENCES semestre(id) ON DELETE RESTRICT",
    "ALTER TABLE matiere ADD COLUMN IF NOT EXISTS publiee_le timestamptz",
    "ALTER TABLE matiere ADD COLUMN IF NOT EXISTS publiee_par uuid",
    "CREATE INDEX IF NOT EXISTS ix_matiere_classe_id ON matiere (classe_id)",
]

DROITS_FINS = [
    "REVOKE UPDATE ON historique_note FROM svc_notes_rw",
    "GRANT DELETE ON affectation TO svc_notes_rw",
    "REVOKE SELECT ON affectation, historique_note, evenement_sortant FROM svc_notes_ro",
    # Le compte de lecture ne voit pas les relevés émis ; les réclamations ne sont jamais supprimées.
    "REVOKE SELECT ON releve_emis FROM svc_notes_ro",
    "REVOKE UPDATE ON releve_emis FROM svc_notes_rw",
]

if __name__ == "__main__":
    log = logs.configurer("notes.migration")
    moteur = Bdd(lire_secret("notes_db_url_migration")).moteur
    Base.metadata.create_all(moteur)
    if moteur.dialect.name == "postgresql":
        with moteur.begin() as cx:
            for ordre in EVOLUTIONS + DROITS_FINS:
                cx.execute(text(ordre))
    log.info("Schéma notes_db à jour, droits fins appliqués.")
