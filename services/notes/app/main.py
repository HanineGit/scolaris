"""Service Notes : F07 à F11."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from scolaris_common import audit, errors, logs, revocation
from scolaris_common.client import ClientInterne
from scolaris_common.config import lire_secret, parametre
from scolaris_common.db import Bdd

from .models import EvenementSortant
from .routes_bilans import router as router_bilans
from .routes_calendrier import router as router_calendrier
from .routes_matieres import router as router_matieres
from .routes_notes import router as router_notes
from .routes_reclamations import router as router_reclamations
from .routes_saisie import router as router_saisie
from .services import tracer


def creer_app(*, url_db: str | None = None, url_db_lecture: str | None = None, client_auth=None,
              client_etudiants=None, publieur=None, relais: bool = True) -> FastAPI:
    log = logs.configurer("notes", parametre("NIVEAU_LOG", "INFO"))
    bdd = Bdd(url_db or lire_secret("notes_db_url"))
    # Deux comptes : lecture-écriture pour les enseignants, lecture seule pour la consultation mobile.
    bdd_lecture = bdd if url_db and not url_db_lecture else Bdd(url_db_lecture or lire_secret("notes_db_url_ro"))

    @asynccontextmanager
    async def cycle(app: FastAPI):
        thread = abonne = None
        if relais:
            thread = audit.Relais(bdd.fabrique, EvenementSortant, publieur or audit.PublieurRabbit(lire_secret("rabbitmq_url")))
            thread.start()
            abonne = revocation.Abonne(app.state.revocations, lire_secret("rabbitmq_url"),
                                       synchroniser=revocation.synchroniseur_http(parametre("URL_AUTH", "http://auth:8000"), "service_token_notes"))
            abonne.start()
        log.info("Service Notes démarré.")
        yield
        for t in (thread, abonne):
            if t:
                t.arreter()

    dev = parametre("ENVIRONNEMENT", "production") == "developpement"
    app = FastAPI(title="Scolaris – Notes", lifespan=cycle,
                  docs_url="/docs" if dev else None, redoc_url=None, openapi_url="/openapi.json" if dev else None)
    app.state.revocations = revocation.Registre()
    app.state.bdd, app.state.bdd_lecture = bdd, bdd_lecture
    app.state.auth = client_auth or ClientInterne(parametre("URL_AUTH", "http://auth:8000"), "service_token_notes")
    app.state.etudiants = client_etudiants or ClientInterne(parametre("URL_ETUDIANTS", "http://etudiants:8000"),
                                                            "service_token_notes")

    def signaler_refus(request: Request, principal):
        with bdd.fabrique() as s:
            tracer(s, request, "ACCES_REFUSE", "REFUSE", acteur=principal, ressource=request.url.path)
            s.commit()

    app.state.signaler_refus = signaler_refus
    errors.installer(app)
    app.include_router(router_bilans)  # en premier : /notes/statistiques avant /notes/{note_id}
    app.include_router(router_calendrier)
    app.include_router(router_matieres)
    app.include_router(router_notes)
    app.include_router(router_saisie)
    app.include_router(router_reclamations)

    @app.get("/sante", include_in_schema=False)
    def sante():
        return {"statut": "ok"}

    return app
