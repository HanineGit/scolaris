"""Sauvegarde chiffrée et restauration des quatre bases (US27, risque R30).

    python scripts/sauvegarde.py sauvegarder            # crée sauvegardes/AAAAMMJJ-HHMMSS/
    python scripts/sauvegarde.py restaurer <dossier>    # restaure et mesure la durée

- Chaque base est exportée avec pg_dump (format personnalisé), puis chiffrée en
  AES-256-GCM avec la clé secrets/backup_key, jamais stockée avec les sauvegardes.
- Le manifeste conserve l'empreinte SHA-256 de chaque export ; la restauration
  refuse un fichier altéré (échec du déchiffrement authentifié ou empreinte différente).
- Planification quotidienne : tâche planifiée Windows ou cron, puis copie du
  dossier chiffré vers le stockage hors site du prestataire.
"""
import base64
import hashlib
import json
import os
# Appels « docker compose » avec des arguments fixes, sans shell.
import subprocess  # nosec B404
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RACINE = Path(__file__).resolve().parents[1]
BASES = ("auth_db", "etudiant_db", "notes_db", "audit_db")
DOSSIER = RACINE / "sauvegardes"


def cle() -> AESGCM:
    return AESGCM(base64.b64decode((RACINE / "secrets" / "backup_key").read_text().strip()))


def compose(*args: str, entree: bytes | None = None) -> bytes:
    r = subprocess.run(["docker", "compose", *args], cwd=RACINE, input=entree, capture_output=True, check=False)  # nosec B603 B607
    if r.returncode != 0:
        raise SystemExit(f"Échec de « docker compose {args[0]} » : {r.stderr.decode(errors='replace')[:400]}")
    return r.stdout


def sauvegarder() -> Path:
    cible = DOSSIER / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    cible.mkdir(parents=True)
    manifeste = {"cree_le": datetime.now(timezone.utc).isoformat(), "bases": {}}
    for base in BASES:
        export = compose("exec", "-T", "-u", "postgres", "postgres", "pg_dump", "-U", "postgres", "-Fc", base)
        nonce = os.urandom(12)
        chiffre = nonce + cle().encrypt(nonce, export, base.encode())  # le nom de la base est lié au chiffré
        (cible / f"{base}.dump.chiffre").write_bytes(chiffre)
        manifeste["bases"][base] = {"sha256": hashlib.sha256(export).hexdigest(), "octets": len(export)}
        print(f"  {base} : {len(export)} octets exportés et chiffrés")
    (cible / "manifeste.json").write_text(json.dumps(manifeste, indent=2), encoding="utf-8")
    print(f"Sauvegarde chiffrée : {cible}")
    return cible


def restaurer(dossier: Path) -> float:
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    debut = time.perf_counter()
    # Tous les fichiers sont vérifiés avant de toucher aux bases : jamais de restauration partielle.
    exports = {}
    for base in BASES:
        chiffre = (dossier / f"{base}.dump.chiffre").read_bytes()
        try:
            exports[base] = cle().decrypt(chiffre[:12], chiffre[12:], base.encode())
        except InvalidTag:
            raise SystemExit(f"{base} : fichier altéré ou clé incorrecte, restauration refusée.") from None
        if hashlib.sha256(exports[base]).hexdigest() != manifeste["bases"][base]["sha256"]:
            raise SystemExit(f"Empreinte incorrecte pour {base} : restauration refusée.")
    for base, export in exports.items():
        compose("exec", "-T", "-u", "postgres", "postgres", "pg_restore", "-U", "postgres", "--clean", "--if-exists",
                "--single-transaction", "-d", base, entree=export)
        print(f"  {base} restaurée")
    duree = time.perf_counter() - debut
    print(f"Restauration terminée en {duree:.1f} s (critère : moins de 4 heures).")
    return duree


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "sauvegarder":
        sauvegarder()
    elif len(sys.argv) == 3 and sys.argv[1] == "restaurer":
        restaurer(Path(sys.argv[2]))
    else:
        print(__doc__)
