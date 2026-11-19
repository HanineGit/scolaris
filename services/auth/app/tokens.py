"""Émission des jetons (F01, risque R02).

- Jeton d'accès : JWT RS256, 15 minutes, signé avec la clé privée du service.
- Jeton intermédiaire de second facteur : JWT de 5 minutes, utilisable
  uniquement sur /auth/mfa/verifier.
- Jeton de rafraîchissement : valeur opaque de 256 bits, stockée hachée,
  à usage unique (rotation), expirant après 15 minutes d'inactivité et au plus
  tard 8 heures après la connexion.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from scolaris_common.config import lire_secret
from scolaris_common.security import ALGORITHME, AUDIENCE, EMETTEUR

from .models import JetonRafraichissement, Utilisateur

DUREE_ACCES = timedelta(minutes=15)
DUREE_MFA = timedelta(minutes=5)
INACTIVITE_MAX = timedelta(minutes=15)
SESSION_MAX = timedelta(hours=8)


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def empreinte(valeur: str) -> str:
    return hashlib.sha256(valeur.encode()).hexdigest()


def _signer(charge: dict) -> str:
    return jwt.encode(charge, lire_secret("jwt_private_key"), algorithm=ALGORITHME)


def jeton_acces(u: Utilisateur, famille: uuid.UUID | None = None) -> str:
    t = maintenant()
    charge = {
        "iss": EMETTEUR, "aud": AUDIENCE, "typ": "access",
        "sub": str(u.id), "role": u.role, "idt": u.identifiant,
        "iat": t, "exp": t + DUREE_ACCES, "jti": str(uuid.uuid4()),
        "t": int(t.timestamp() * 1000),  # instant d'émission à la milliseconde, comparé aux révocations
    }
    if famille:
        charge["fam"] = str(famille)  # identifie la session courante dans l'espace sécurité
    if u.etudiant_id:
        charge["etu"] = str(u.etudiant_id)
    return _signer(charge)


def jeton_mfa(u: Utilisateur) -> str:
    t = maintenant()
    return _signer({
        "iss": EMETTEUR, "aud": AUDIENCE, "typ": "mfa",
        "sub": str(u.id), "iat": t, "exp": t + DUREE_MFA, "jti": str(uuid.uuid4()),
    })


def nouveau_rafraichissement(session, u: Utilisateur, famille=None, debut=None) -> str:
    valeur = secrets.token_urlsafe(32)
    t = maintenant()
    debut = debut or t
    session.add(JetonRafraichissement(
        utilisateur_id=u.id,
        famille=famille or uuid.uuid4(),
        debut_famille=debut,
        empreinte=empreinte(valeur),
        expire_le=min(t + INACTIVITE_MAX, debut + SESSION_MAX),
    ))
    return valeur


def nouveau_jeton_activation() -> str:
    return secrets.token_urlsafe(32)
