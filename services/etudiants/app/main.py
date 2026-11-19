"""Service Étudiants : F04, F05, F06, F15 (classes), F16 (import)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from scolaris_common import audit, errors, logs, revocation
from scolaris_common.client import ClientInterne
from scolaris_common.config import lire_secret, parametre
from scolaris_common.db import Bdd

from .models import EvenementSortant
from .routes import interne, router, tracer
from .routes_classes import classes, interne_classes, scolarite


def creer_app(*, url_db: str | None = None, client_auth=None, publieur=None, relais: bool = True) -> FastAPI:
    log = logs.configurer("etudiants", parametre("NIVEAU_LOG", "INFO"))
    bdd = Bdd(url_db or lire_secret("etudiant_db_url"))

    @asynccontextmanager
    async def cycle(app: FastAPI):
        thread = abonne = None
        if relais:
            thread = audit.Relais(bdd.fabrique, EvenementSortant, publieur or audit.PublieurRabbit(lire_secret("rabbitmq_url")))
            thread.start()
            abonne = revocation.Abonne(app.state.revocations, lire_secret("rabbitmq_url"),
                                       synchroniser=revocation.synchroniseur_http(parametre("URL_AUTH", "http://auth:8000"), "service_token_etudiants"))
            abonne.start()
        log.info("Service Étudiants démarré.")
        yield
        for t in (thread, abonne):
            if t:
                t.arreter()

    dev = parametre("ENVIRONNEMENT", "production") == "developpement"
    app = FastAPI(title="Scolaris – Étudiants", lifespan=cycle,
                  docs_url="/docs" if dev else None, redoc_url=None, openapi_url="/openapi.json" if dev else None)
    app.state.revocations = revocation.Registre()
    app.state.bdd = bdd
    app.state.auth = client_auth or ClientInterne(parametre("URL_AUTH", "http://auth:8000"), "service_token_etudiants")

    def signaler_refus(request: Request, principal):
        with bdd.fabrique() as s:
            tracer(s, request, "ACCES_REFUSE", "REFUSE", acteur=principal, ressource=request.url.path)
            s.commit()

    app.state.signaler_refus = signaler_refus
    errors.installer(app)
    # « scolarite » avant « router » : /statistiques et /import ne doivent pas être lus comme un identifiant.
    app.include_router(scolarite)
    app.include_router(router)
    app.include_router(classes)
    app.include_router(interne)
    app.include_router(interne_classes)

    @app.get("/sante", include_in_schema=False)
    def sante():
        return {"statut": "ok"}

    return app
