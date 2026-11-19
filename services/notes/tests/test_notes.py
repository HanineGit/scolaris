"""Tests du service Notes, alignés sur les critères de succès R14 à R22."""
import uuid
from datetime import date, timedelta

import pytest
from scolaris_common.testing import entetes

from conftest import AUTRE_ENSEIGNANT_ID, ENSEIGNANT_ID, evenements


def admin():
    return entetes("ADMINISTRATEUR", identifiant="a.tchinda")


def prof(sub=ENSEIGNANT_ID):
    return entetes("ENSEIGNANT", sub=sub, identifiant="j.abena")


def ajouter_etudiant(env, matricule="ETU-2026-0142", statut="ACTIF"):
    i = str(uuid.uuid4())
    env.etudiants[i] = {"id": i, "matricule": matricule, "nom": "DIALLO", "prenom": "Aminata", "statut": statut}
    return i


@pytest.fixture
def matiere(env):
    r = env.client.post("/api/v1/matieres", headers=admin(), json={"code": "INF341", "libelle": "Sécurité logicielle", "coefficient": "3"})
    assert r.status_code == 201, r.text
    m = r.json()["id"]
    assert env.client.post(f"/api/v1/matieres/{m}/affectations", headers=admin(),
                           json={"enseignant_id": str(ENSEIGNANT_ID)}).status_code == 201
    return m


def publier(env, matiere):
    r = env.client.post(f"/api/v1/matieres/{matiere}/publication", headers=admin())
    assert r.status_code == 200, r.text


def saisir(env, matiere, etudiant, valeur="15.50", type_evaluation="EXAMEN", jour=None, entete=None):
    return env.client.post("/api/v1/notes", headers=entete or prof(), json={
        "matiere_id": matiere, "etudiant_id": etudiant, "type_evaluation": type_evaluation,
        "date_evaluation": (jour or date.today()).isoformat(), "valeur": valeur})


# --- F07 ---

def test_matiere_non_supprimable(env, matiere):
    """R14 : aucune route DELETE sur une matière, seulement la désactivation."""
    assert env.client.delete(f"/api/v1/matieres/{matiere}", headers=admin()).status_code == 405
    r = env.client.patch(f"/api/v1/matieres/{matiere}", headers=admin(), json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False


def test_affectation_refusee_pour_un_non_enseignant(env, matiere):
    r = env.client.post(f"/api/v1/matieres/{matiere}/affectations", headers=admin(), json={"enseignant_id": str(uuid.uuid4())})
    assert r.status_code == 422


def test_mes_matieres(env, matiere):
    corps = env.client.get("/api/v1/enseignants/moi/matieres", headers=prof()).json()
    assert [m["code"] for m in corps["elements"]] == ["INF341"]
    autre = env.client.get("/api/v1/enseignants/moi/matieres", headers=prof(AUTRE_ENSEIGNANT_ID)).json()
    assert autre["elements"] == []


# --- F08 ---

def test_saisie_reussie_et_tracee(env, matiere):
    e = ajouter_etudiant(env)
    r = saisir(env, matiere, e)
    assert r.status_code == 201, r.text
    assert r.json()["valeur"] == "15.50" and r.json()["saisie_par"] == "j.abena"
    ev = evenements(env)[-1]
    assert ev["action"] == "NOTE_AJOUTEE" and ev["acteur_identifiant"] == "j.abena"


@pytest.mark.parametrize("valeur", ["21", "-1", "12.345", "abc"])
def test_valeur_hors_bornes_refusee(env, matiere, valeur):
    """R15 : une note de 21 ou négative est refusée."""
    assert saisir(env, matiere, ajouter_etudiant(env), valeur=valeur).status_code == 422


def test_date_future_refusee(env, matiere):
    assert saisir(env, matiere, ajouter_etudiant(env), jour=date.today() + timedelta(days=1)).status_code == 422


def test_double_saisie_refusee(env, matiere):
    e = ajouter_etudiant(env)
    assert saisir(env, matiere, e).status_code == 201
    assert saisir(env, matiere, e, valeur="10").status_code == 409


def test_saisie_hors_affectation_refusee_et_journalisee(env, matiere):
    """R16 : un enseignant non affecté reçoit 403, avec un événement ACCES_REFUSE."""
    r = saisir(env, matiere, ajouter_etudiant(env), entete=prof(AUTRE_ENSEIGNANT_ID))
    assert r.status_code == 403
    assert evenements(env)[-1]["action"] == "ACCES_REFUSE"


def test_administrateur_ne_saisit_pas_de_note(env, matiere):
    """Séparation des tâches : l'administrateur ne peut pas écrire de note."""
    assert saisir(env, matiere, ajouter_etudiant(env), entete=admin()).status_code == 403


def test_etudiant_archive_ne_peut_pas_etre_note(env, matiere):
    assert saisir(env, matiere, ajouter_etudiant(env, statut="ARCHIVE")).status_code == 409


# --- F09, F10 ---

def test_modification_motivee_avec_historique(env, matiere):
    """R18, R19 : historique complet, auteur tiré du jeton, événement avec avant/après."""
    note = saisir(env, matiere, ajouter_etudiant(env), valeur="13").json()
    r = env.client.put(f"/api/v1/notes/{note['id']}", headers=prof(),
                       json={"valeur": "14", "motif": "Erreur de report sur la question 4", "version": note["version"]})
    assert r.status_code == 200, r.text
    hist = env.client.get(f"/api/v1/notes/{note['id']}/historique", headers=prof()).json()["elements"]
    assert [(h["avant"], h["apres"]) for h in hist] == [("13.00", "14.00"), (None, "13.00")]
    ev = evenements(env)[-1]
    assert ev["action"] == "NOTE_MODIFIEE" and ev["details"]["avant"] == "13.00" and ev["details"]["apres"] == "14.00"


@pytest.mark.parametrize("motif", ["court", "<script>x</script> motif long", ""])
def test_motif_obligatoire_et_propre(env, matiere, motif):
    note = saisir(env, matiere, ajouter_etudiant(env)).json()
    r = env.client.put(f"/api/v1/notes/{note['id']}", headers=prof(), json={"valeur": "10", "motif": motif, "version": 1})
    assert r.status_code == 422


def test_modification_sur_version_perimee(env, matiere):
    note = saisir(env, matiere, ajouter_etudiant(env)).json()
    corps = {"valeur": "11", "motif": "Correction du barème exercice 2", "version": 1}
    assert env.client.put(f"/api/v1/notes/{note['id']}", headers=prof(), json=corps).status_code == 200
    corps["valeur"] = "12"
    assert env.client.put(f"/api/v1/notes/{note['id']}", headers=prof(), json=corps).status_code == 409


def test_modification_par_un_enseignant_non_affecte(env, matiere):
    note = saisir(env, matiere, ajouter_etudiant(env)).json()
    r = env.client.put(f"/api/v1/notes/{note['id']}", headers=prof(AUTRE_ENSEIGNANT_ID),
                       json={"valeur": "20", "motif": "Tentative de modification", "version": 1})
    assert r.status_code == 403


def test_aucune_suppression_de_note(env, matiere):
    note = saisir(env, matiere, ajouter_etudiant(env)).json()
    assert env.client.delete(f"/api/v1/notes/{note['id']}", headers=prof()).status_code == 405


def test_consultation_par_matiere_et_filtre_matricule(env, matiere):
    a = ajouter_etudiant(env, "ETU-2026-0142")
    b = ajouter_etudiant(env, "ETU-2026-0143")
    saisir(env, matiere, a)
    saisir(env, matiere, b)
    tout = env.client.get(f"/api/v1/matieres/{matiere}/notes", headers=prof()).json()
    assert tout["total"] == 2 and tout["elements"][0]["etudiant"]["matricule"].startswith("ETU-")
    un = env.client.get(f"/api/v1/matieres/{matiere}/notes?matricule=ETU-2026-0143", headers=prof()).json()
    assert un["total"] == 1
    assert env.client.get(f"/api/v1/matieres/{matiere}/notes?taille=100", headers=prof()).status_code == 422


# --- F11 ---

def test_etudiant_ne_voit_que_ses_notes(env, matiere):
    """R20 : l'identité vient du jeton ; un paramètre étranger est ignoré."""
    moi = ajouter_etudiant(env, "ETU-2026-0142")
    autre = ajouter_etudiant(env, "ETU-2026-0143")
    saisir(env, matiere, moi, valeur="16")
    saisir(env, matiere, autre, valeur="9")
    publier(env, matiere)
    entete = entetes("ETUDIANT", etudiant_id=uuid.UUID(moi))
    corps = env.client.get(f"/api/v1/etudiants/moi/notes?etudiant_id={autre}", headers=entete).json()
    assert [n["valeur"] for n in corps["notes"]] == ["16.00"]
    assert corps["moyenne_generale"] == "16.00"
    assert corps["matieres"][0]["coefficient"] == "3.0"


def test_note_modifiee_signalee_a_l_etudiant(env, matiere):
    moi = ajouter_etudiant(env)
    note = saisir(env, matiere, moi, valeur="12").json()
    env.client.put(f"/api/v1/notes/{note['id']}", headers=prof(), json={"valeur": "13", "motif": "Correction de barème", "version": 1})
    publier(env, matiere)
    corps = env.client.get("/api/v1/etudiants/moi/notes", headers=entetes("ETUDIANT", etudiant_id=uuid.UUID(moi))).json()
    assert corps["notes"][0]["modifiee_le"] is not None


def test_enseignant_ne_peut_pas_utiliser_la_route_etudiant(env, matiere):
    assert env.client.get("/api/v1/etudiants/moi/notes", headers=prof()).status_code == 403
