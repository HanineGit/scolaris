"""Service Authentification : F01, F02, F03."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from scolaris_common import audit, errors, logs, revocation
from scolaris_common.config import lire_secret, parametre

from . import db
from .mail import ExpediteurSmtp
from .models import EvenementSortant
from .routes_admin import router as router_admin
from .routes_auth import router as router_auth
from .routes_internes import router as router_internes
from .routes_moi import admin_router as router_securite
from .routes_moi import router as router_moi
from .services import tracer


def creer_app(*, url_db: str | None = None, expediteur=None, publieur=None, relais: bool = True) -> FastAPI:
    log = logs.configurer("auth", parametre("NIVEAU_LOG", "INFO"))
    db.initialiser(url_db)

    @asynccontextmanager
    async def cycle(app: FastAPI):
        thread = abonne = None
        if relais:
            thread = audit.Relais(db.fabrique(), EvenementSortant, publieur or audit.PublieurRabbit(lire_secret("rabbitmq_url")))
            thread.start()
            url = lire_secret("rabbitmq_url")
            app.state.publier_revocation = lambda uid, instant: revocation.publier(url, uid, instant)
            # Plusieurs instances du service se tiennent informées par le même bus.
            abonne = revocation.Abonne(app.state.revocations, url, synchroniser=_revocations_en_base)
            abonne.start()
        log.info("Service d'authentification démarré.")
        yield
        for t in (thread, abonne):
            if t:
                t.arreter()

    # Documentation OpenAPI désactivée hors développement : pas de cartographie offerte.
    dev = parametre("ENVIRONNEMENT", "production") == "developpement"
    app = FastAPI(title="Scolaris – Authentification", lifespan=cycle,
                  docs_url="/docs" if dev else None, redoc_url=None, openapi_url="/openapi.json" if dev else None)
    app.state.expediteur = expediteur or ExpediteurSmtp()
    app.state.revocations = revocation.Registre()
    app.state.publier_revocation = None

    def _revocations_en_base():
        from sqlalchemy import select

        from .models import Revocation
        limite = revocation.maintenant_ms() - revocation.DUREE_CONSERVATION_S * 1000
        with db.fabrique()() as s:
            return [(str(r.utilisateur_id), r.instant_ms)
                    for r in s.scalars(select(Revocation).where(Revocation.instant_ms >= limite))]

    def signaler_refus(request: Request, principal):
        with db.fabrique()() as s:
            tracer(s, request, "ACCES_REFUSE", "REFUSE", acteur=principal,
                   ressource=request.url.path)
            s.commit()

    app.state.signaler_refus = signaler_refus
    errors.installer(app)
    app.include_router(router_auth)
    app.include_router(router_admin)
    app.include_router(router_internes)
    app.include_router(router_moi)
    app.include_router(router_securite)

    @app.get("/sante", include_in_schema=False)
    def sante():
        return {"statut": "ok"}

    return app
