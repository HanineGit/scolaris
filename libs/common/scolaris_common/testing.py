"""Outils de test partagés : secrets temporaires et jetons signés par rôle."""
import base64
import os
import secrets as pysecrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from . import config
from .security import ALGORITHME, AUDIENCE, EMETTEUR

NOMS_JETONS_SERVICE = ("service_token_etudiants", "service_token_notes", "service_token_audit",
                       "service_token_notifications")


def preparer_secrets(dossier: Path) -> Path:
    cle = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (dossier / "jwt_private_key").write_bytes(cle.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (dossier / "jwt_public_key").write_bytes(cle.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    (dossier / "mfa_encryption_key").write_text(base64.b64encode(os.urandom(32)).decode())
    for nom in NOMS_JETONS_SERVICE:
        (dossier / nom).write_text(pysecrets.token_urlsafe(32))
    os.environ["SCOLARIS_SECRETS_DIR"] = str(dossier)
    config.SECRETS_DIR = dossier
    config.lire_secret.cache_clear()
    return dossier


def jeton(role: str, *, sub: uuid.UUID | None = None, etudiant_id: uuid.UUID | None = None,
          identifiant: str = "test", duree: timedelta = timedelta(minutes=15)) -> str:
    t = datetime.now(timezone.utc)
    charge = {"iss": EMETTEUR, "aud": AUDIENCE, "typ": "access", "sub": str(sub or uuid.uuid4()),
              "role": role, "idt": identifiant, "iat": t, "exp": t + duree}
    if etudiant_id:
        charge["etu"] = str(etudiant_id)
    return jwt.encode(charge, config.lire_secret("jwt_private_key"), algorithm=ALGORITHME)


def entetes(role: str, **kw) -> dict:
    return {"Authorization": f"Bearer {jeton(role, **kw)}"}


def entete_service(nom: str) -> dict:
    return {"X-Service-Token": config.lire_secret(nom)}


class ClientFactice:
    """Remplace un ClientInterne : réponses programmées par (méthode, chemin)."""

    def __init__(self):
        self.reponses = {}
        self.appels = []

    def programmer(self, methode: str, chemin: str, reponse):
        self.reponses[(methode, chemin)] = reponse

    def _appel(self, methode, chemin, json=None):
        self.appels.append((methode, chemin, json))
        chemin_seul = chemin.split("?")[0]
        reponse = self.reponses.get((methode, chemin_seul))
        if reponse is None:
            # Motif terminé par « * » : correspondance par préfixe (ex. /internal/comptes/*).
            for (m, motif), r in self.reponses.items():
                if m == methode and motif.endswith("*") and chemin_seul.startswith(motif[:-1]):
                    reponse = r
                    break
        if isinstance(reponse, Exception):
            raise reponse
        # Une fonction reçoit le corps JSON (POST, PATCH) ou le chemin (GET).
        return reponse(json if json is not None else chemin) if callable(reponse) else reponse

    def get(self, chemin, **kw):
        return self._appel("GET", chemin)

    def post(self, chemin, json=None):
        return self._appel("POST", chemin, json)

    def patch(self, chemin, json=None):
        return self._appel("PATCH", chemin, json)
