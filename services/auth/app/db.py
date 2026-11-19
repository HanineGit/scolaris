from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scolaris_common.config import lire_secret

_moteur = None
_fabrique = None


def initialiser(url: str | None = None):
    """Crée le moteur. L'URL (avec mot de passe) provient d'un secret Docker."""
    global _moteur, _fabrique
    url = url or lire_secret("auth_db_url")
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        options = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    _moteur = create_engine(url, **options)
    _fabrique = sessionmaker(bind=_moteur, expire_on_commit=False)
    return _moteur


def moteur():
    return _moteur


def fabrique():
    return _fabrique


def session():
    """Dépendance FastAPI : une session par requête."""
    with _fabrique() as s:
        yield s
