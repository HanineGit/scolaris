"""Tests de la saisie groupée, des statistiques et des exports (F21, F22, F23)."""
import io
import uuid
from datetime import date

import pytest

from conftest import AUTRE_ENSEIGNANT_ID, evenements
from test_notes import admin, ajouter_etudiant, matiere, prof, publier, saisir  # noqa: F401  (fixture)


@pytest.fixture
def classe(env, matiere):
    membres = [ajouter_etudiant(env, f"ETU-2026-02{i:02d}") for i in range(4)]
    classe_id = str(uuid.uuid4())
    env.classes[classe_id] = {"id": classe_id, "code": "L2-INFO", "libelle": "L2 Informatique", "membres": membres}
    assert env.client.patch(f"/api/v1/matieres/{matiere}", headers=admin(), json={"classe_id": classe_id}).status_code == 200
    return membres


def evaluation(membres, valeurs, type_evaluation="EXAMEN"):
    return {"type_evaluation": type_evaluation, "date_evaluation": date.today().isoformat(),
            "notes": [{"etudiant_id": e, "valeur": v} for e, v in zip(membres, valeurs)]}


def test_grille_presente_la_classe_et_les_notes_deja_saisies(env, matiere, classe):
    saisir(env, matiere, classe[0], valeur="12")
    r = env.client.get(f"/api/v1/matieres/{matiere}/grille?type_evaluation=EXAMEN&date_evaluation={date.today()}",
                       headers=prof())
    corps = r.json()
    assert r.status_code == 200 and corps["saisie_possible"] is True and len(corps["lignes"]) == 4
    assert corps["lignes"][0]["note"]["valeur"] == "12.00" and corps["lignes"][1]["note"] is None
    assert env.client.get(f"/api/v1/matieres/{matiere}/grille?type_evaluation=EXAMEN&date_evaluation={date.today()}",
                          headers=prof(AUTRE_ENSEIGNANT_ID)).status_code == 403


def test_saisie_de_toute_la_classe_tracee_note_par_note(env, matiere, classe):
    r = env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(),
                        json=evaluation(classe, ["8", "12.5", "15", "17.75"]))
    assert r.status_code == 201 and r.json()["enregistrees"] == 4
    ajouts = [e for e in evenements(env) if e["action"] == "NOTE_AJOUTEE"]
    assert len(ajouts) == 4 and ajouts[0]["details"]["saisie"] == "groupee"


def test_saisie_groupee_tout_ou_rien(env, matiere, classe):
    saisir(env, matiere, classe[2], valeur="10")
    r = env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(), json=evaluation(classe, ["8", "9", "11", "13"]))
    assert r.status_code == 409 and r.json()["erreur"]["code"] == "DOUBLON"
    intrus = evaluation(classe[:2] + [ajouter_etudiant(env, "ETU-2026-0999")], ["8", "9", "10"], "TP")
    assert env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(), json=intrus).json()["erreur"]["code"] == "HORS_CLASSE"
    hors_bornes = evaluation(classe, ["8", "21", "10", "10"], "TP")
    assert env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(), json=hors_bornes).status_code == 422
    doublon = evaluation([classe[0], classe[0]], ["8", "9"], "TP")
    assert env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(), json=doublon).status_code == 422
    tp = env.client.get(f"/api/v1/matieres/{matiere}/grille?type_evaluation=TP&date_evaluation={date.today()}", headers=prof()).json()
    assert all(l["note"] is None for l in tp["lignes"])  # rien n'a été enregistré


def test_saisie_groupee_impossible_sans_classe_ou_apres_publication(env, matiere):
    r = env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(),
                        json=evaluation([ajouter_etudiant(env)], ["10"]))
    assert r.json()["erreur"]["code"] == "SANS_CLASSE"


def test_saisie_groupee_refusee_apres_publication(env, matiere, classe):
    saisir(env, matiere, classe[0])
    publier(env, matiere)
    r = env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(), json=evaluation(classe[1:], ["10", "11", "12"]))
    assert r.json()["erreur"]["code"] == "NOTES_PUBLIEES"


def test_statistiques_exactes(env, matiere, classe):
    env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(), json=evaluation(classe, ["6", "9.5", "12", "16"]))
    s = env.client.get(f"/api/v1/matieres/{matiere}/statistiques", headers=prof()).json()
    e = s["evaluations"][0]
    assert (e["nombre"], e["moyenne"], e["mediane"], e["minimum"], e["maximum"]) == (4, 10.88, 10.75, 6.0, 16.0)
    assert e["taux_reussite"] == 50.0 and e["repartition"] == [0, 1, 1, 0, 1, 0, 1]  # 12 compte dans 12–14
    assert env.client.get(f"/api/v1/matieres/{matiere}/statistiques", headers=admin()).status_code == 200
    assert env.client.get(f"/api/v1/matieres/{matiere}/statistiques", headers=prof(AUTRE_ENSEIGNANT_ID)).status_code == 403


def test_export_excel_neutralise_les_formules_et_est_journalise(env, matiere, classe):
    env.etudiants[classe[0]]["nom"] = "=HYPERLINK(\"http://pirate\",\"clic\")"
    env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(), json=evaluation(classe, ["10", "11", "12", "13"]))
    r = env.client.get(f"/api/v1/matieres/{matiere}/export?format=xlsx", headers=prof())
    assert r.status_code == 200 and r.headers["content-disposition"] == 'attachment; filename="notes-INF341.xlsx"'
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(r.content)).active
    noms = [ws.cell(row=i, column=2).value for i in range(5, ws.max_row + 1)]
    assert "'=HYPERLINK(\"http://pirate\",\"clic\")" in noms
    assert all(ws.cell(row=i, column=2).data_type == "s" for i in range(5, ws.max_row + 1))
    ev = evenements(env)[-1]
    assert ev["action"] == "EXPORT_NOTES" and ev["details"] == {"matiere": "INF341", "format": "xlsx", "lignes": 4}


def test_export_pdf_et_droits(env, matiere, classe):
    env.client.post(f"/api/v1/matieres/{matiere}/evaluations", headers=prof(), json=evaluation(classe, ["10", "11", "12", "13"]))
    r = env.client.get(f"/api/v1/matieres/{matiere}/export?format=pdf", headers=admin())
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and b"/JavaScript" not in r.content
    assert env.client.get(f"/api/v1/matieres/{matiere}/export?format=csv", headers=prof()).status_code == 422
    assert env.client.get(f"/api/v1/matieres/{matiere}/export?format=pdf", headers=prof(AUTRE_ENSEIGNANT_ID)).status_code == 403
