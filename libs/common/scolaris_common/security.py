"""Vérification des jetons et contrôle d'accès, appliqués par chaque service.

Principe de confiance zéro : même derrière la passerelle, chaque microservice
revérifie la signature, l'émetteur, l'audience, l'expiration et le rôle.
Seule la clé publique est distribuée aux services ; la clé privée reste dans le
service d'authentification.
"""
import hmac
from dataclasses import dataclass
from typing import Callable
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import lire_secret
from .errors import ErreurMetier

EMETTEUR = "scolaris-auth"
AUDIENCE = "scolaris-api"
ALGORITHME = "RS256"

ETUDIANT = "ETUDIANT"
ENSEIGNANT = "ENSEIGNANT"
ADMINISTRATEUR = "ADMINISTRATEUR"
ROLES = {ETUDIANT, ENSEIGNANT, ADMINISTRATEUR}

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Identité extraite du jeton : seule source de confiance sur l'appelant."""
    id: UUID
    role: str
    etudiant_id: UUID | None
    identifiant: str


def cle_publique() -> str:
    return lire_secret("jwt_public_key")


def decoder_jeton(jeton: str, type_attendu: str = "access", cle: str | None = None) -> dict:
    try:
        charge = jwt.decode(
            jeton,
            cle or cle_publique(),
            algorithms=[ALGORITHME],  # liste fermée : pas de « alg: none » ni de HS256
            audience=AUDIENCE,
            issuer=EMETTEUR,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.PyJWTError:
        raise ErreurMetier(401, "Session invalide ou expirée.", "SESSION_INVALIDE")
    if charge.get("typ") != type_attendu:
        raise ErreurMetier(401, "Session invalide ou expirée.", "SESSION_INVALIDE")
    return charge


def principal_courant(
    request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> Principal:
    if cred is None or cred.scheme.lower() != "bearer":
        raise ErreurMetier(401, "Authentification requise.", "AUTH_REQUISE")
    charge = decoder_jeton(cred.credentials)
    if charge.get("role") not in ROLES:
        raise ErreurMetier(401, "Session invalide ou expirée.", "SESSION_INVALIDE")
    # Révocation immédiate : jeton émis avant la désactivation, le changement de rôle
    # ou la réinitialisation du second facteur de ce compte.
    registre = getattr(request.app.state, "revocations", None)
    emis_ms = int(charge.get("t") or int(charge["iat"]) * 1000)
    if registre is not None and registre.est_revoque(charge["sub"], emis_ms):
        raise ErreurMetier(401, "Session révoquée. Veuillez vous reconnecter.", "SESSION_REVOQUEE")
    principal = Principal(
        id=UUID(charge["sub"]),
        role=charge["role"],
        etudiant_id=UUID(charge["etu"]) if charge.get("etu") else None,
        identifiant=charge.get("idt", ""),
    )
    request.state.principal = principal
    return principal


def exiger_roles(*roles: str) -> Callable:
    """Dépendance FastAPI : refuse (403) tout appelant dont le rôle n'est pas listé.

    Le refus est signalé au service via app.state.signaler_refus pour être
    journalisé (événement ACCES_REFUSE).
    """
    autorises = set(roles)

    def verifier(request: Request, principal: Principal = Depends(principal_courant)) -> Principal:
        if principal.role not in autorises:
            signaler = getattr(request.app.state, "signaler_refus", None)
            if signaler:
                signaler(request, principal)
            raise ErreurMetier(403, "Accès refusé.", "ACCES_REFUSE")
        return principal

    return verifier


def exiger_service(*noms_secrets: str) -> Callable:
    """Dépendance pour les routes /internal : jeton de service partagé.

    Ces routes ne sont jamais exposées par la passerelle ; le jeton empêche en
    plus un conteneur non autorisé du réseau interne de les appeler.
    """

    def verifier(request: Request) -> None:
        fourni = request.headers.get("x-service-token", "").encode()
        # Chaque service appelant possède son propre jeton ; comparaison à temps constant.
        valide = any(hmac.compare_digest(fourni, lire_secret(n).encode()) for n in noms_secrets)
        if not fourni or not valide:
            raise ErreurMetier(401, "Authentification requise.", "AUTH_REQUISE")

    return verifier
