"""Gestion des erreurs sans divulgation d'information technique.

- Les erreurs inattendues sont journalisées intégralement côté serveur et le
  client ne reçoit qu'un message générique avec l'identifiant de corrélation.
- Les erreurs de validation indiquent le champ en cause et la règle, sans
  jamais renvoyer la valeur saisie.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logs import id_correlation

log = logging.getLogger("erreurs")

MESSAGES = {
    400: "Requête invalide.",
    401: "Authentification requise.",
    403: "Accès refusé.",
    404: "Ressource introuvable.",
    405: "Méthode non autorisée.",
    409: "Conflit avec l'état actuel de la ressource.",
    413: "Requête trop volumineuse.",
    415: "Type de contenu non pris en charge.",
    422: "Données invalides.",
    429: "Trop de requêtes. Réessayez plus tard.",
}


class ErreurMetier(Exception):
    """Erreur prévue, dont le message est destiné à l'utilisateur."""

    def __init__(self, statut: int, message: str, code: str | None = None):
        self.statut = statut
        self.message = message
        self.code = code or f"E{statut}"


def corps(statut: int, message: str, code: str | None = None, details=None) -> dict:
    contenu = {"erreur": {"code": code or f"E{statut}", "message": message, "id_correlation": id_correlation.get()}}
    if details:
        contenu["erreur"]["details"] = details
    return contenu


def installer(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation(request: Request, call_next):
        entrant = request.headers.get("x-correlation-id", "")
        # On n'accepte qu'un UUID ; sinon on en génère un (pas d'injection dans les journaux).
        try:
            valeur = str(uuid.UUID(entrant))
        except ValueError:
            valeur = str(uuid.uuid4())
        jeton = id_correlation.set(valeur)
        try:
            reponse = await call_next(request)
        finally:
            id_correlation.reset(jeton)
        reponse.headers["X-Correlation-Id"] = valeur
        # Aucune donnée de notes ne doit rester dans un cache (risque R17).
        reponse.headers["Cache-Control"] = "no-store"
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        return reponse

    @app.exception_handler(ErreurMetier)
    async def erreur_metier(request: Request, exc: ErreurMetier):
        return JSONResponse(corps(exc.statut, exc.message, exc.code), status_code=exc.statut)

    @app.exception_handler(StarletteHTTPException)
    async def erreur_http(request: Request, exc: StarletteHTTPException):
        message = MESSAGES.get(exc.status_code, "Erreur.")
        return JSONResponse(corps(exc.status_code, message), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def erreur_validation(request: Request, exc: RequestValidationError):
        details = []
        for e in exc.errors():
            champ = ".".join(str(p) for p in e.get("loc", []) if p not in ("body", "query", "path"))
            # Le message de règle est conservé, la valeur saisie (« input ») est retirée.
            details.append({"champ": champ, "regle": e.get("msg", "invalide")})
        return JSONResponse(corps(422, MESSAGES[422], "E422", details), status_code=422)

    @app.exception_handler(Exception)
    async def erreur_inattendue(request: Request, exc: Exception):
        log.exception("Erreur inattendue sur %s %s", request.method, request.url.path)
        return JSONResponse(corps(500, "Une erreur est survenue."), status_code=500)
