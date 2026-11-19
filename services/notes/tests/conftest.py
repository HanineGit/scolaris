import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ENSEIGNANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUTRE_ENSEIGNANT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


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

    etudiants, classes = {}, {}

    def etudiant_par_id(chemin):
        return etudiants[chemin.rsplit("/", 1)[1]]

    def etudiant_par_matricule(chemin):
        from scolaris_common.errors import ErreurMetier
        matricule = chemin.split("matricule=")[1]
        for e in etudiants.values():
            if e["matricule"] == matricule:
                return e
        raise ErreurMetier(404, "Aucun étudiant ne porte ce matricule.")

    def classe_par_id(chemin):
        from scolaris_common.errors import ErreurMetier
        c = classes.get(chemin.rsplit("/", 1)[1])
        if c is None:
            raise ErreurMetier(404, "Classe introuvable.")
        return {**c, "etudiants": [etudiants[i] for i in c["membres"]]}

    ce = ClientFactice()
    ce.programmer("GET", "/internal/classes/*", classe_par_id)
    ce.programmer("GET", "/internal/etudiants/*", etudiant_par_id)
    ce.programmer("GET", "/internal/etudiants", etudiant_par_matricule)
    ce.programmer("POST", "/internal/etudiants/lot", lambda corps: {i: etudiants[i] for i in corps["ids"] if i in etudiants})

    ca = ClientFactice()
    ca.programmer("GET", "/internal/comptes", [{"id": str(ENSEIGNANT_ID), "nom": "ABENA", "prenom": "Jean"}])
    ca.programmer("GET", "/internal/comptes/*", lambda chemin: {
        "role": "ENSEIGNANT" if chemin.endswith(str(ENSEIGNANT_ID)) or chemin.endswith(str(AUTRE_ENSEIGNANT_ID)) else "ETUDIANT",
        "statut": "ACTIF"})

    app = creer_app(url_db="sqlite://", client_auth=ca, client_etudiants=ce, relais=False)
    Base.metadata.create_all(app.state.bdd.moteur)

    class Env:
        pass

    e = Env()
    e.client, e.bdd, e.etudiants, e.classes = TestClient(app, raise_server_exceptions=False), app.state.bdd, etudiants, classes
    yield e
    Base.metadata.drop_all(app.state.bdd.moteur)


def _boite(env):
    from app.models import EvenementSortant
    with env.bdd.fabrique() as s:
        return [e.contenu for e in s.query(EvenementSortant).order_by(EvenementSortant.cree_le)]


def evenements(env):
    """Événements d'audit seulement (les notifications partagent la boîte d'envoi)."""
    return [e for e in _boite(env) if e.get("genre") != "notification"]


def notifications(env):
    return [e for e in _boite(env) if e.get("genre") == "notification"]
