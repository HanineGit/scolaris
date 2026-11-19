"""Connexion à la base propre à chaque service."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class Bdd:
    def __init__(self, url: str):
        # Pool fixe, sans connexions temporaires : chaque ouverture coûte une négociation TLS
        # et une authentification SCRAM, trop chères pour être répétées sous la charge (US27).
        # 10 connexions par processus restent sous les 200 autorisées par PostgreSQL.
        options = {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 0}
        if url.startswith("sqlite"):
            from sqlalchemy.pool import StaticPool

            options = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        self.moteur = create_engine(url, **options)
        self.fabrique = sessionmaker(bind=self.moteur, expire_on_commit=False)

    def session(self):
        """Dépendance FastAPI : une session par requête, fermée à la fin."""
        with self.fabrique() as s:
            yield s
