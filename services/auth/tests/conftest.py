"""Environnement de test : base SQLite en mémoire, secrets générés, e-mails et bus simulés."""
import base64
import os
import re
import secrets as pysecrets
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session", autouse=True)
def secrets_de_test(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("secrets")
    cle = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (dossier / "jwt_private_key").write_bytes(cle.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (dossier / "jwt_public_key").write_bytes(cle.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    (dossier / "mfa_encryption_key").write_text(base64.b64encode(os.urandom(32)).decode())
    (dossier / "service_token_etudiants").write_text(pysecrets.token_urlsafe(32))
    (dossier / "service_token_notes").write_text(pysecrets.token_urlsafe(32))
    (dossier / "service_token_audit").write_text(pysecrets.token_urlsafe(32))
    (dossier / "service_token_notifications").write_text(pysecrets.token_urlsafe(32))
    os.environ["SCOLARIS_SECRETS_DIR"] = str(dossier)
    os.environ["URL_ACTIVATION"] = "https://scolaris.test/activation"
    from scolaris_common import config
    config.SECRETS_DIR = dossier
    config.lire_secret.cache_clear()
    return dossier


@pytest.fixture
def env():
    from fastapi.testclient import TestClient

    from app import db
    from app.mail import ExpediteurMemoire
    from app.main import creer_app
    from app.models import Base
    from scolaris_common.audit import PublieurMemoire

    expediteur = ExpediteurMemoire()
    app = creer_app(url_db="sqlite://", expediteur=expediteur, publieur=PublieurMemoire(), relais=False)
    Base.metadata.create_all(db.moteur())
    client = TestClient(app, raise_server_exceptions=False)

    class Env:
        pass

    e = Env()
    e.client, e.expediteur, e.db = client, expediteur, db
    yield e
    Base.metadata.drop_all(db.moteur())


def jeton_du_dernier_mail(expediteur) -> str:
    return re.search(r"#jeton=([A-Za-z0-9_\-]+)", expediteur.envoyes[-1]["texte"]).group(1)


def _boite(env) -> list[dict]:
    from app.models import EvenementSortant

    with env.db.fabrique()() as s:
        return [e.contenu for e in s.query(EvenementSortant).order_by(EvenementSortant.cree_le)]


def evenements(env) -> list[str]:
    """Actions d'audit seulement (les notifications partagent la boîte d'envoi)."""
    return [e["action"] for e in _boite(env) if e.get("genre") != "notification"]


def notifications(env) -> list[dict]:
    return [e for e in _boite(env) if e.get("genre") == "notification"]
