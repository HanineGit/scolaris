"""Tests des réclamations (F19)."""
import uuid
from datetime import timedelta

import pytest
from scolaris_common.testing import entetes

from conftest import AUTRE_ENSEIGNANT_ID, ENSEIGNANT_ID, evenements, notifications
from test_notes import admin, ajouter_etudiant, matiere, prof, publier, saisir  # noqa: F401  (fixture)

MOTIF = "Je pense qu'un exercice n'a pas été comptabilisé dans la note."


def eleve(etu):
    return entetes("ETUDIANT", etudiant_id=uuid.UUID(etu))


@pytest.fixture
def note_publiee(env, matiere):
    etu = ajouter_etudiant(env)
    note = saisir(env, matiere, etu, valeur="9.5").json()
    publier(env, matiere)
    return etu, note


def deposer(env, etu, note_id, motif=MOTIF):
    return env.client.post("/api/v1/etudiants/moi/reclamations", headers=eleve(etu), json={"note_id": note_id, "motif": motif})


def test_reclamation_deposee_tracee_et_enseignant_prevenu(env, note_publiee):
    etu, note = note_publiee
    r = deposer(env, etu, note["id"])
    assert r.status_code == 201 and r.json()["statut"] == "SOUMISE"
    assert evenements(env)[-1]["action"] == "RECLAMATION_SOUMISE"
    notif = notifications(env)[-1]
    assert notif["categorie"] == "RECLAMATION" and notif["destinataires"] == [{"utilisateur_id": str(ENSEIGNANT_ID)}]
    assert deposer(env, etu, note["id"]).json()["erreur"]["code"] == "DEJA_OUVERTE"
    assert env.client.get("/api/v1/etudiants/moi/reclamations", headers=eleve(etu)).json()["elements"][0]["statut"] == "SOUMISE"


def test_note_d_un_autre_ou_non_publiee_introuvable(env, matiere, note_publiee):
    _, note = note_publiee
    intrus = ajouter_etudiant(env, "ETU-2026-0777")
    assert deposer(env, intrus, note["id"]).status_code == 404
    brouillon = saisir(env, matiere, intrus, type_evaluation="TP")
    assert brouillon.status_code == 409  # matière publiée : plus de saisie
    assert deposer(env, intrus, str(uuid.uuid4())).status_code == 404


def test_motif_controle_et_delai_de_quinze_jours(env, note_publiee):
    etu, note = note_publiee
    assert deposer(env, etu, note["id"], motif="trop court").status_code == 422
    assert deposer(env, etu, note["id"], motif=MOTIF + "<script>").status_code == 422
    from app.models import Matiere
    with env.bdd.fabrique() as s:
        m = s.query(Matiere).one()
        m.publiee_le = m.publiee_le - timedelta(days=16)
        s.commit()
    assert deposer(env, etu, note["id"]).json()["erreur"]["code"] == "DELAI_DEPASSE"


def test_acceptation_modifie_la_note_avec_historique_et_previent_l_etudiant(env, note_publiee):
    etu, note = note_publiee
    rec = deposer(env, etu, note["id"]).json()
    corps = {"decision": "ACCEPTEE", "reponse": "Exercice 3 recompté.", "nouvelle_valeur": "11", "version": rec["version"]}
    assert env.client.put(f"/api/v1/reclamations/{rec['id']}", headers=prof(AUTRE_ENSEIGNANT_ID), json=corps).status_code == 403
    r = env.client.put(f"/api/v1/reclamations/{rec['id']}", headers=prof(), json=corps)
    assert r.status_code == 200 and r.json()["statut"] == "ACCEPTEE" and r.json()["note"]["valeur"] == "11.00"
    actions = [e["action"] for e in evenements(env)]
    assert actions[-2:] == ["NOTE_MODIFIEE", "RECLAMATION_TRAITEE"]
    historique = env.client.get(f"/api/v1/notes/{note['id']}/historique", headers=prof()).json()["elements"]
    assert historique[0]["avant"] == "9.50" and historique[0]["motif"].startswith("Réclamation acceptée")
    assert notifications(env)[-1]["destinataires"] == [{"etudiant_id": etu}]
    vue = env.client.get("/api/v1/etudiants/moi/notes", headers=eleve(etu)).json()
    assert vue["notes"][0]["valeur"] == "11.00" and vue["notes"][0]["modifiee_le"] is not None
    corps["version"] = r.json()["version"]
    assert env.client.put(f"/api/v1/reclamations/{rec['id']}", headers=prof(), json=corps).json()["erreur"]["code"] == "CLOSE"


def test_rejet_sans_modification_et_regles_de_decision(env, note_publiee):
    etu, note = note_publiee
    rec = deposer(env, etu, note["id"]).json()
    incoherent = {"decision": "REJETEE", "reponse": "Barème appliqué correctement.", "nouvelle_valeur": "12", "version": 1}
    assert env.client.put(f"/api/v1/reclamations/{rec['id']}", headers=prof(), json=incoherent).status_code == 422
    sans_valeur = {"decision": "ACCEPTEE", "reponse": "Barème appliqué correctement.", "version": 1}
    assert env.client.put(f"/api/v1/reclamations/{rec['id']}", headers=prof(), json=sans_valeur).status_code == 422
    r = env.client.put(f"/api/v1/reclamations/{rec['id']}", headers=prof(),
                       json={"decision": "REJETEE", "reponse": "Barème appliqué correctement.", "version": 1})
    assert r.json()["statut"] == "REJETEE" and r.json()["note"]["valeur"] == "9.50"


def test_limite_de_reclamations_ouvertes(env, matiere):
    etu = ajouter_etudiant(env)
    notes = [saisir(env, matiere, etu, type_evaluation=t, jour=None).json() for t in ("EXAMEN", "TP", "CONTROLE_CONTINU", "RATTRAPAGE")]
    from datetime import date
    notes += [saisir(env, matiere, etu, type_evaluation="TP", jour=date.today() - timedelta(days=d)).json() for d in (1, 2)]
    publier(env, matiere)
    codes = [deposer(env, etu, n["id"]).status_code for n in notes]
    assert codes == [201] * 5 + [409]


def test_listes_enseignant_et_administrateur(env, note_publiee):
    etu, note = note_publiee
    deposer(env, etu, note["id"])
    liste = env.client.get("/api/v1/enseignants/moi/reclamations", headers=prof()).json()["elements"]
    assert len(liste) == 1 and liste[0]["etudiant"]["matricule"] == "ETU-2026-0142"
    assert env.client.get("/api/v1/enseignants/moi/reclamations", headers=prof(AUTRE_ENSEIGNANT_ID)).json()["elements"] == []
    assert len(env.client.get("/api/v1/reclamations?statut=SOUMISE", headers=admin()).json()["elements"]) == 1
    assert env.client.get("/api/v1/reclamations", headers=prof()).status_code == 403
