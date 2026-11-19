import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session", autouse=True)
def secrets_de_test(tmp_path_factory):
    from scolaris_common.testing import preparer_secrets
    return preparer_secrets(tmp_path_factory.mktemp("secrets"))


@pytest.fixture
def env():
    from fastapi.testclient import TestClient

    from app.main import creer_app
    from app.models import Base
    from scolaris_common.testing import ClientFactice

    auth = ClientFactice()
    auth.programmer("POST", "/internal/comptes/etudiants", lambda corps: {"utilisateur_id": str(uuid.uuid4())})
    auth.programmer("POST", "/internal/comptes/etats", {})
    app = creer_app(url_db="sqlite://", client_auth=auth, relais=False)
    Base.metadata.create_all(app.state.bdd.moteur)

    class Env:
        pass

    e = Env()
    e.client, e.auth, e.bdd = TestClient(app, raise_server_exceptions=False), auth, app.state.bdd
    yield e
    Base.metadata.drop_all(app.state.bdd.moteur)


def evenements(env):
    from app.models import EvenementSortant
    with env.bdd.fabrique() as s:
        return [e.contenu for e in s.query(EvenementSortant).order_by(EvenementSortant.cree_le)]
