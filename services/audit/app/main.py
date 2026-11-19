"""Service Audit : F12 (réception, chaînage) et F13 (consultation)."""
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from scolaris_common import errors, logs, revocation
from scolaris_common.audit import construire_evenement
from scolaris_common.config import lire_secret, parametre
from scolaris_common.db import Bdd

from . import chaine
from .routes import router


def creer_app(*, url_db: str | None = None, demarrer_threads: bool = True) -> FastAPI:
    log = logs.configurer("audit", parametre("NIVEAU_LOG", "INFO"))
    bdd = Bdd(url_db or lire_secret("audit_db_url"))

    @asynccontextmanager
    async def cycle(app: FastAPI):
        threads = []
        if demarrer_threads:
            threads = [chaine.Consommateur(bdd.fabrique, lire_secret("rabbitmq_url")),
                       chaine.VerificateurQuotidien(bdd.fabrique),
                       revocation.Abonne(app.state.revocations, lire_secret("rabbitmq_url"),
                                         synchroniser=revocation.synchroniseur_http(
                                             parametre("URL_AUTH", "http://auth:8000"), "service_token_audit"))]
            for t in threads:
                t.start()
        log.info("Service Audit démarré.")
        yield
        for t in threads:
            t.arreter()

    dev = parametre("ENVIRONNEMENT", "production") == "developpement"
    app = FastAPI(title="Scolaris – Audit", lifespan=cycle,
                  docs_url="/docs" if dev else None, redoc_url=None, openapi_url="/openapi.json" if dev else None)
    app.state.bdd = bdd
    app.state.revocations = revocation.Registre()

    def signaler_refus(request: Request, principal):
        # Le service Audit écrit directement ses propres refus dans la chaîne.
        chaine.inserer(bdd.fabrique, construire_evenement(
            service="audit", action="ACCES_REFUSE", resultat="REFUSE", acteur_id=principal.id,
            acteur_identifiant=principal.identifiant, role=principal.role, ressource=request.url.path,
            adresse_ip=request.headers.get("x-real-ip") or (request.client.host if request.client else None)))

    app.state.signaler_refus = signaler_refus
    errors.installer(app)
    app.include_router(router)

    @app.get("/sante", include_in_schema=False)
    def sante():
        return {"statut": "ok"}

    return app
