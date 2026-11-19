"""Tests des classes, des inscriptions et de l'import d'une promotion (F15, F16)."""
from scolaris_common.calendrier import annee_academique
from scolaris_common.testing import entete_service, entetes

from conftest import evenements


def admin():
    return entetes("ADMINISTRATEUR", identifiant="a.tchinda")


def creer_classe(env, code="L2-INFO", **kw):
    corps = {"code": code, "libelle": "Licence 2 Informatique", "filiere": "Informatique", "niveau": "L2",
             "annee_academique": annee_academique(), **kw}
    return env.client.post("/api/v1/classes", headers=admin(), json=corps)


def ajouter(env, email="a.diallo@etu.univ-exemple.cm", **kw):
    return env.client.post("/api/v1/etudiants", headers=admin(),
                           json={"nom": "Diallo", "prenom": "Aminata", "email": email, **kw})


def test_creation_de_classe_journalisee_et_code_unique_par_annee(env):
    r = creer_classe(env, code="l2-info")
    assert r.status_code == 201 and r.json()["code"] == "L2-INFO"
    assert evenements(env)[-1]["action"] == "CLASSE_CREEE"
    assert creer_classe(env).status_code == 409


def test_classe_reservee_a_l_administrateur_et_valeurs_controlees(env):
    corps = {"code": "L2", "libelle": "x" * 3, "filiere": "Info", "niveau": "L2", "annee_academique": annee_academique()}
    assert env.client.post("/api/v1/classes", headers=entetes("ENSEIGNANT"), json=corps).status_code == 403
    assert creer_classe(env, niveau="L9").status_code == 422
    assert creer_classe(env, annee_academique="2026-2028").status_code == 422
    assert creer_classe(env, libelle="<script>").status_code == 422


def test_ajout_direct_dans_une_classe_et_filtre(env):
    classe = creer_classe(env).json()
    r = ajouter(env, classe_id=classe["id"])
    assert r.status_code == 201 and r.json()["classe"] == "L2-INFO"
    ajouter(env, email="autre@etu.univ-exemple.cm")
    liste = env.client.get(f"/api/v1/etudiants?classe_id={classe['id']}", headers=admin()).json()
    assert liste["total"] == 1


def test_inscription_tracee_et_classe_fermee_refusee(env):
    classe = creer_classe(env).json()
    e = ajouter(env).json()
    r = env.client.put(f"/api/v1/etudiants/{e['id']}/classe", headers=admin(),
                       json={"classe_id": classe["id"], "version": e["version"]})
    assert r.status_code == 200 and r.json()["classe"] == "L2-INFO"
    ev = evenements(env)[-1]
    assert ev["action"] == "ETUDIANT_INSCRIT" and ev["details"]["apres"] == {"classe": "L2-INFO"}
    env.client.patch(f"/api/v1/classes/{classe['id']}", headers=admin(), json={"active": False})
    autre = ajouter(env, email="b@etu.univ-exemple.cm").json()
    r = env.client.put(f"/api/v1/etudiants/{autre['id']}/classe", headers=admin(),
                       json={"classe_id": classe["id"], "version": autre["version"]})
    assert r.status_code == 422


def test_statistiques_de_scolarite(env):
    classe = creer_classe(env).json()
    ajouter(env, classe_id=classe["id"])
    ajouter(env, email="b@etu.univ-exemple.cm")
    s = env.client.get("/api/v1/etudiants/statistiques", headers=admin()).json()
    assert s["actifs"] == 2 and s["sans_classe"] == 1
    assert s["par_classe"] == [{"code": "L2-INFO", "libelle": "Licence 2 Informatique", "effectif": 1}]
    assert env.client.get("/api/v1/etudiants/statistiques", headers=entetes("ENSEIGNANT")).status_code == 403


CSV_OK = "nom;prenom;email\nNgono;Paul;p.ngono@etu.univ-exemple.cm\nEbode;Grâce;g.ebode@etu.univ-exemple.cm\n"


def test_import_verifie_sans_rien_enregistrer_puis_confirme(env):
    classe = creer_classe(env).json()
    r = env.client.post("/api/v1/etudiants/import", headers=admin(), json={"contenu": CSV_OK, "classe_id": classe["id"]})
    assert r.status_code == 200 and r.json()["valides"] == 2 and r.json()["importes"] == 0
    assert env.client.get("/api/v1/etudiants", headers=admin()).json()["total"] == 0
    r = env.client.post("/api/v1/etudiants/import", headers=admin(),
                        json={"contenu": CSV_OK, "classe_id": classe["id"], "confirmer": True})
    assert r.json()["importes"] == 2
    assert len([a for a in env.auth.appels if a[1] == "/internal/comptes/etudiants"]) == 2
    actions = [e["action"] for e in evenements(env)]
    assert actions.count("ETUDIANT_AJOUTE") == 2 and actions[-1] == "ETUDIANTS_IMPORTES"


def test_import_refuse_entierement_si_une_ligne_est_invalide(env):
    ajouter(env, email="p.ngono@etu.univ-exemple.cm")
    csv = CSV_OK + "=HYPERLINK(\"http://x\");Jean;pas-une-adresse\nMbarga;Luc;g.ebode@etu.univ-exemple.cm\n"
    r = env.client.post("/api/v1/etudiants/import", headers=admin(), json={"contenu": csv, "confirmer": True})
    corps = r.json()
    assert corps["importes"] == 0 and corps["invalides"] == 3
    erreurs = {l["ligne"]: l["erreurs"] for l in corps["rapport"]}
    assert erreurs[2] == ["adresse déjà utilisée"]
    assert erreurs[4] == ["email invalide", "nom invalide"]
    assert erreurs[5] == ["adresse en double dans le fichier"]
    assert "HYPERLINK" not in r.text  # la saisie refusée n'est pas renvoyée
    assert env.client.get("/api/v1/etudiants", headers=admin()).json()["total"] == 1


def test_import_borne_et_format_controle(env):
    trop = "nom,prenom,email\n" + "".join(f"Nom,Prenom,e{i}@etu.univ-exemple.cm\n" for i in range(1001))
    assert env.client.post("/api/v1/etudiants/import", headers=admin(), json={"contenu": trop}).json()["erreur"]["code"] == "TROP_DE_LIGNES"
    assert env.client.post("/api/v1/etudiants/import", headers=admin(), json={"contenu": "a;b\n1;2"}).status_code == 422
    assert env.client.post("/api/v1/etudiants/import", headers=entetes("ENSEIGNANT"), json={"contenu": CSV_OK}).status_code == 403


def test_liste_interne_d_une_classe_reservee_au_service_notes(env):
    classe = creer_classe(env).json()
    ajouter(env, classe_id=classe["id"])
    assert env.client.get(f"/internal/classes/{classe['id']}").status_code == 401
    r = env.client.get(f"/internal/classes/{classe['id']}", headers=entete_service("service_token_notes"))
    assert r.status_code == 200 and r.json()["etudiants"][0]["nom"] == "DIALLO"
    assert "email" not in r.json()["etudiants"][0]  # minimisation : la saisie n'a pas besoin de l'adresse
