"""Tests des semestres, fenêtres de saisie et de la publication des notes (F17, F18)."""
import uuid
from datetime import date, timedelta

from scolaris_common.calendrier import annee_academique
from scolaris_common.testing import entetes

from conftest import evenements, notifications
from test_notes import admin, ajouter_etudiant, matiere, prof, publier, saisir  # noqa: F401  (fixture)


def semestre(env, debut=None, fin=None, numero=1):
    corps = {"annee_academique": annee_academique(), "numero": numero}
    if debut:
        corps |= {"saisie_debut": debut.isoformat(), "saisie_fin": fin.isoformat()}
    r = env.client.post("/api/v1/semestres", headers=admin(), json=corps)
    assert r.status_code == 201, r.text
    return r.json()


def rattacher(env, matiere, **champs):
    r = env.client.patch(f"/api/v1/matieres/{matiere}", headers=admin(), json=champs)
    assert r.status_code == 200, r.text
    return r.json()


def test_semestre_unique_reserve_a_l_administrateur_et_fenetre_coherente(env):
    semestre(env)
    corps = {"annee_academique": annee_academique(), "numero": 1}
    assert env.client.post("/api/v1/semestres", headers=admin(), json=corps).status_code == 409
    assert env.client.post("/api/v1/semestres", headers=prof(), json={**corps, "numero": 2}).status_code == 403
    a_l_envers = {**corps, "numero": 2, "saisie_debut": "2026-12-10", "saisie_fin": "2026-12-01"}
    assert env.client.post("/api/v1/semestres", headers=admin(), json=a_l_envers).status_code == 422
    assert env.client.get("/api/v1/semestres", headers=prof()).json()["elements"][0]["saisie_ouverte"] is False


def test_saisie_refusee_hors_de_la_fenetre_puis_acceptee_quand_elle_s_ouvre(env, matiere):
    s = semestre(env)
    rattacher(env, matiere, semestre_id=s["id"])
    etu = ajouter_etudiant(env)
    r = saisir(env, matiere, etu)
    assert r.status_code == 409 and r.json()["erreur"]["code"] == "SAISIE_FERMEE"
    aujourd_hui = date.today()
    r = env.client.put(f"/api/v1/semestres/{s['id']}/fenetre", headers=admin(),
                       json={"saisie_debut": (aujourd_hui - timedelta(days=1)).isoformat(),
                             "saisie_fin": (aujourd_hui + timedelta(days=7)).isoformat()})
    assert r.json()["saisie_ouverte"] is True
    assert evenements(env)[-1]["action"] == "FENETRE_SAISIE_MODIFIEE"
    assert saisir(env, matiere, etu).status_code == 201
    env.client.post(f"/api/v1/semestres/{s['id']}/fermeture", headers=admin())
    assert saisir(env, matiere, etu, type_evaluation="TP").json()["erreur"]["code"] == "SAISIE_FERMEE"


def test_notes_invisibles_avant_publication(env, matiere):
    etu = ajouter_etudiant(env)
    saisir(env, matiere, etu, valeur="14")
    vue = env.client.get("/api/v1/etudiants/moi/notes", headers=entetes("ETUDIANT", etudiant_id=uuid.UUID(etu))).json()
    assert vue["notes"] == [] and vue["moyenne_generale"] is None
    publier(env, matiere)
    vue = env.client.get("/api/v1/etudiants/moi/notes", headers=entetes("ETUDIANT", etudiant_id=uuid.UUID(etu))).json()
    assert [n["valeur"] for n in vue["notes"]] == ["14.00"]


def test_publication_verrouille_la_matiere_et_notifie_sans_reveler_la_note(env, matiere):
    membres = [ajouter_etudiant(env, f"ETU-2026-01{i}") for i in range(3)]
    classe_id = str(uuid.uuid4())
    env.classes[classe_id] = {"id": classe_id, "code": "L2-INFO", "membres": membres}
    rattacher(env, matiere, classe_id=classe_id)
    note = saisir(env, matiere, membres[0], valeur="11.25").json()
    assert env.client.post(f"/api/v1/matieres/{matiere}/publication", headers=prof()).status_code == 403
    publier(env, matiere)
    assert evenements(env)[-1]["action"] == "NOTES_PUBLIEES"
    notif = notifications(env)[-1]
    assert notif["categorie"] == "NOTES" and len(notif["destinataires"]) == 3
    assert "11" not in notif["message"]  # aucune valeur de note dans la notification
    r = env.client.put(f"/api/v1/notes/{note['id']}", headers=prof(),
                       json={"valeur": "12", "motif": "Correction de barème", "version": note["version"]})
    assert r.status_code == 409 and r.json()["erreur"]["code"] == "NOTES_PUBLIEES"
    assert saisir(env, matiere, membres[1]).json()["erreur"]["code"] == "NOTES_PUBLIEES"
    assert env.client.post(f"/api/v1/matieres/{matiere}/publication", headers=admin()).status_code == 409


def test_publication_sans_note_refusee(env, matiere):
    r = env.client.post(f"/api/v1/matieres/{matiere}/publication", headers=admin())
    assert r.status_code == 409 and r.json()["erreur"]["code"] == "AUCUNE_NOTE"


def test_depublication_motivee_et_tracee_en_alerte(env, matiere):
    saisir(env, matiere, ajouter_etudiant(env))
    publier(env, matiere)
    assert env.client.post(f"/api/v1/matieres/{matiere}/depublication", headers=admin(), json={"motif": "court"}).status_code == 422
    r = env.client.post(f"/api/v1/matieres/{matiere}/depublication", headers=admin(),
                        json={"motif": "Ouverture de la session de rattrapage"})
    assert r.status_code == 200
    ev = evenements(env)[-1]
    assert ev["action"] == "NOTES_DEPUBLIEES" and ev["resultat"] == "ALERTE"


def test_rattachement_a_une_classe_inconnue_refuse(env, matiere):
    r = env.client.patch(f"/api/v1/matieres/{matiere}", headers=admin(), json={"classe_id": str(uuid.uuid4())})
    assert r.status_code == 422 and r.json()["erreur"]["code"] == "CLASSE"
