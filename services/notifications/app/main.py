"""Service Notifications : F28 (centre de notifications, alimenté par le bus)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from scolaris_common import errors, logs, revocation
from scolaris_common.config import lire_secret, parametre
from scolaris_common.db import Bdd

from . import reception
from .routes import router


def creer_app(*, url_db: str | None = None, demarrer_threads: bool = True) -> FastAPI:
    log = logs.configurer("notifications", parametre("NIVEAU_LOG", "INFO"))
    bdd = Bdd(url_db or lire_secret("notifications_db_url"))

    @asynccontextmanager
    async def cycle(app: FastAPI):
        threads = []
        if demarrer_threads:
            threads = [reception.Consommateur(bdd.fabrique, lire_secret("rabbitmq_url")),
                       revocation.Abonne(app.state.revocations, lire_secret("rabbitmq_url"),
                                         synchroniser=revocation.synchroniseur_http(
                                             parametre("URL_AUTH", "http://auth:8000"), "service_token_notifications"))]
            for t in threads:
                t.start()
        log.info("Service Notifications démarré.")
        yield
        for t in threads:
            t.arreter()

    dev = parametre("ENVIRONNEMENT", "production") == "developpement"
    app = FastAPI(title="Scolaris – Notifications", lifespan=cycle,
                  docs_url="/docs" if dev else None, redoc_url=None, openapi_url="/openapi.json" if dev else None)
    app.state.bdd = bdd
    app.state.revocations = revocation.Registre()
    errors.installer(app)
    app.include_router(router)

    @app.get("/sante", include_in_schema=False)
    def sante():
        return {"statut": "ok"}

    return app
