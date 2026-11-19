"""Tests du centre de notifications (F28) : cloisonnement, validation des messages du bus, idempotence."""
import uuid

import pytest
from scolaris_common import audit
from scolaris_common.testing import entetes

from app import reception


def message(**kw):
    base = {"genre": "notification", "id": str(uuid.uuid4()), "horodatage": "2026-11-19T10:00:00+00:00",
            "categorie": "NOTES", "titre": "Nouvelles notes disponibles", "message": "Les notes de Réseaux sont publiées.",
            "lien": "/notes", "destinataires": []}
    return base | kw


def test_message_produit_par_la_boite_d_envoi_accepte_tel_quel(env):
    """Contrat : ce que publient les autres services est exactement ce que ce service accepte."""
    capture = []

    class Session:
        def add(self, ligne):
            capture.append(ligne.contenu)

    class Modele:
        def __init__(self, contenu):
            self.contenu = contenu

    etu = uuid.uuid4()
    audit.notifier(Session(), Modele, categorie="NOTES", titre="Titre", message="Texte", etudiants=[etu], lien="/notes")
    assert reception.enregistrer(env.bdd.fabrique, capture[0]) == 1


def test_chacun_ne_voit_que_ses_notifications(env):
    moi, autre, etu = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    reception.enregistrer(env.bdd.fabrique, message(destinataires=[{"utilisateur_id": str(moi)}]))
    reception.enregistrer(env.bdd.fabrique, message(destinataires=[{"utilisateur_id": str(autre)}]))
    reception.enregistrer(env.bdd.fabrique, message(categorie="RECLAMATION", destinataires=[{"etudiant_id": str(etu)}]))
    mes = env.client.get("/api/v1/notifications", headers=entetes("ENSEIGNANT", sub=moi)).json()
    assert mes["non_lues"] == 1 and len(mes["elements"]) == 1
    # Un étudiant reçoit aussi ce qui vise sa fiche (identifiant « etu » du jeton).
    eleve = env.client.get("/api/v1/notifications", headers=entetes("ETUDIANT", etudiant_id=etu)).json()
    assert [n["categorie"] for n in eleve["elements"]] == ["RECLAMATION"]
    assert env.client.get("/api/v1/notifications").status_code == 401


def test_marquer_lue_seulement_les_siennes(env):
    moi, autre = uuid.uuid4(), uuid.uuid4()
    reception.enregistrer(env.bdd.fabrique, message(destinataires=[{"utilisateur_id": str(moi)}, {"utilisateur_id": str(autre)}]))
    n = env.client.get("/api/v1/notifications", headers=entetes("ENSEIGNANT", sub=moi)).json()["elements"][0]
    assert env.client.post(f"/api/v1/notifications/{n['id']}/lecture", headers=entetes("ENSEIGNANT", sub=autre)).status_code == 404
    assert env.client.post(f"/api/v1/notifications/{n['id']}/lecture", headers=entetes("ENSEIGNANT", sub=moi)).status_code == 204
    assert env.client.get("/api/v1/notifications", headers=entetes("ENSEIGNANT", sub=moi)).json()["non_lues"] == 0
    assert env.client.get("/api/v1/notifications", headers=entetes("ENSEIGNANT", sub=autre)).json()["non_lues"] == 1
    env.client.post("/api/v1/notifications/lecture", headers=entetes("ENSEIGNANT", sub=autre))
    assert env.client.get("/api/v1/notifications?non_lues=true", headers=entetes("ENSEIGNANT", sub=autre)).json()["elements"] == []


def test_message_redelivre_enregistre_une_seule_fois(env):
    m = message(destinataires=[{"utilisateur_id": str(uuid.uuid4())}])
    assert reception.enregistrer(env.bdd.fabrique, m) == 1
    assert reception.enregistrer(env.bdd.fabrique, m) == 0


@pytest.mark.parametrize("piege", [
    {"lien": "https://site-pirate.example/connexion"},          # hameçonnage : lien externe refusé
    {"lien": "//site-pirate.example"},
    {"lien": "//sitepirate"},
    {"lien": "/notes/../../x"},
    {"categorie": "ADMIN"},
    {"destinataires": [{"utilisateur_id": str(uuid.uuid4()), "etudiant_id": str(uuid.uuid4())}]},
    {"destinataires": []},
    {"titre": "x" * 121},
    {"champ_inattendu": True},
    {"genre": "audit"},
])
def test_message_du_bus_hors_liste_blanche_ecarte(env, piege):
    m = message(destinataires=[{"utilisateur_id": str(uuid.uuid4())}]) | piege
    with pytest.raises(ValueError):
        reception.enregistrer(env.bdd.fabrique, m)
