"""Tests du relevé vérifiable, de la synthèse étudiante, des indicateurs et de la délibération (F20, F24–F26)."""
import uuid

from scolaris_common.testing import entetes

from conftest import ENSEIGNANT_ID, evenements
from test_notes import admin, ajouter_etudiant, prof, publier, saisir


def eleve(etu):
    return entetes("ETUDIANT", etudiant_id=uuid.UUID(etu))


def matiere(env, code, coefficient, classe_id=None):
    r = env.client.post("/api/v1/matieres", headers=admin(),
                        json={"code": code, "libelle": f"Matière {code}", "coefficient": coefficient, "classe_id": classe_id})
    m = r.json()["id"]
    env.client.post(f"/api/v1/matieres/{m}/affectations", headers=admin(), json={"enseignant_id": str(ENSEIGNANT_ID)})
    return m


def test_synthese_ponderee_et_matieres_a_surveiller(env):
    etu = ajouter_etudiant(env)
    m1, m2, m3 = matiere(env, "MAT1", "3"), matiere(env, "MAT2", "1"), matiere(env, "MAT3", "2")
    saisir(env, m1, etu, valeur="14")
    saisir(env, m2, etu, valeur="8")
    saisir(env, m3, etu, valeur="20")  # jamais publiée : ignorée
    publier(env, m1)
    publier(env, m2)
    s = env.client.get("/api/v1/etudiants/moi/synthese", headers=eleve(etu)).json()
    assert s["moyenne_generale"] == "12.50" and s["mention"] == "Assez bien"  # (14×3 + 8×1) / 4
    assert s["matieres"] == 2 and s["matieres_validees"] == 1
    assert s["a_surveiller"] == [{"code": "MAT2", "libelle": "Matière MAT2", "moyenne": "8.00"}]
    assert env.client.get("/api/v1/etudiants/moi/synthese", headers=prof()).status_code == 403


def test_releve_pdf_verifiable_publiquement_avec_matricule_masque(env):
    etu = ajouter_etudiant(env, "ETU-2026-0142")
    m = matiere(env, "MAT1", "2")
    saisir(env, m, etu, valeur="15")
    publier(env, m)
    r = env.client.get("/api/v1/etudiants/moi/releve", headers=eleve(etu))
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and b"/JavaScript" not in r.content
    assert evenements(env)[-1]["action"] == "RELEVE_EMIS"
    from app.models import ReleveEmis
    with env.bdd.fabrique() as s:
        code = s.query(ReleveEmis).one().code
    assert r.headers["x-code-verification"] == code
    v = env.client.get(f"/api/v1/verification/{code}").json()  # aucune authentification
    assert v["valide"] is True and v["matricule"] == "ETU-2026-**42" and v["moyenne_generale"] == "15.00"
    assert "nom" not in v and "prenom" not in v
    assert env.client.get(f"/api/v1/verification/{'0' * 32}").json() == {"valide": False}
    assert env.client.get("/api/v1/verification/' OR 1=1 --").status_code in (404, 422)


def test_releve_limite_a_dix_par_jour(env):
    etu = ajouter_etudiant(env)
    codes = [env.client.get("/api/v1/etudiants/moi/releve", headers=eleve(etu)).status_code for _ in range(11)]
    assert codes == [200] * 10 + [429]


def test_indicateurs_reserves_a_l_administrateur(env):
    etu = ajouter_etudiant(env)
    m = matiere(env, "MAT1", "2")
    saisir(env, m, etu, valeur="11")
    i = env.client.get("/api/v1/notes/statistiques", headers=admin()).json()
    assert i["notes_total"] == 1 and i["notes_7_jours"] == 1 and len(i["saisies_par_jour"]) == 14
    assert i["matieres_publiees"] == 0 and i["moyennes_par_matiere"][0]["moyenne"] == 11.0
    assert env.client.get("/api/v1/notes/statistiques", headers=prof()).status_code == 403


def test_deliberation_rang_decision_et_proces_verbal(env):
    membres = [ajouter_etudiant(env, f"ETU-2026-030{i}") for i in range(3)]
    classe_id = str(uuid.uuid4())
    env.classes[classe_id] = {"id": classe_id, "code": "L2-INFO", "libelle": "L2 Informatique", "membres": membres}
    m1, m2 = matiere(env, "MAT1", "2", classe_id), matiere(env, "MAT2", "1", classe_id)
    for etu, (a, b) in zip(membres[:2], (("12", "9"), ("7", "10"))):
        saisir(env, m1, etu, valeur=a)
        saisir(env, m2, etu, valeur=b)
    d = env.client.get(f"/api/v1/classes/{classe_id}/deliberation", headers=admin()).json()
    res = {r["etudiant"]["matricule"]: r for r in d["resultats"]}
    assert res["ETU-2026-0300"]["moyenne_generale"] == "11.00" and res["ETU-2026-0300"]["decision"] == "ADMIS"
    assert res["ETU-2026-0300"]["rang"] == 1
    assert res["ETU-2026-0301"]["moyenne_generale"] == "8.00" and res["ETU-2026-0301"]["decision"] == "AJOURNE"
    assert res["ETU-2026-0302"]["decision"] == "INCOMPLET" and "rang" not in res["ETU-2026-0302"]
    assert d["synthese"] == {"effectif": 3, "admis": 1, "ajournes": 1, "non_publiees": ["MAT1", "MAT2"]}
    pv = env.client.get(f"/api/v1/classes/{classe_id}/deliberation?format=pdf", headers=admin())
    assert pv.status_code == 200 and pv.content.startswith(b"%PDF")
    assert evenements(env)[-1]["action"] == "DELIBERATION_EXPORTEE"
    assert env.client.get(f"/api/v1/classes/{classe_id}/deliberation", headers=prof()).status_code == 403
