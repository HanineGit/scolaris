"""Tests du service Étudiants, alignés sur les critères de succès R08 à R13."""
import pytest
from scolaris_common.errors import ErreurMetier
from scolaris_common.testing import entete_service, entetes

from conftest import evenements


def admin():
    return entetes("ADMINISTRATEUR", identifiant="a.tchinda")



def ajouter(env, nom="Diallo", prenom="Aminata", email="a.diallo@etu.univ-exemple.cm"):
    return env.client.post("/api/v1/etudiants", headers=entetes("ADMINISTRATEUR"),
                           json={"nom": nom, "prenom": prenom, "email": email})


def test_ajout_genere_le_matricule_et_cree_le_compte(env):
    r = ajouter(env)
    assert r.status_code == 201, r.text
    corps = r.json()
    assert corps["matricule"].startswith("ETU-") and corps["matricule"].endswith("-0001")
    assert corps["nom"] == "DIALLO"
    assert env.auth.appels[0][1] == "/internal/comptes/etudiants"
    ev = evenements(env)[-1]
    assert ev["action"] == "ETUDIANT_AJOUTE" and ev["acteur_identifiant"] == "test"


def test_matricules_successifs(env):
    ajouter(env)
    r = ajouter(env, "Essomba", "Paul", "p.essomba@etu.univ-exemple.cm")
    assert r.json()["matricule"].endswith("-0002")


def test_matricule_impose_par_le_client_refuse(env):
    r = env.client.post("/api/v1/etudiants", headers=admin(),
                        json={"nom": "Diallo", "prenom": "Aminata", "email": "a@etu.univ-exemple.cm", "matricule": "ETU-2026-9999"})
    assert r.status_code == 422


@pytest.mark.parametrize("nom", ["<script>alert(1)</script>", "Robert'); DROP TABLE etudiant;--", "A", "Diallo3"])
def test_injection_et_caracteres_interdits_refuses(env, nom):
    """R08 : liste blanche, rejet en 422 sans écho de la valeur."""
    r = ajouter(env, nom=nom)
    assert r.status_code == 422
    assert nom not in r.text


def test_doublon_email_refuse(env):
    """R09."""
    ajouter(env)
    r = ajouter(env, "Autre", "Personne", "a.diallo@etu.univ-exemple.cm")
    assert r.status_code == 409


def test_echec_du_service_auth_annule_l_ajout(env):
    env.auth.programmer("POST", "/internal/comptes/etudiants",
                        ErreurMetier(503, "Service temporairement indisponible.", "INDISPONIBLE"))
    assert ajouter(env).status_code == 503
    liste = env.client.get("/api/v1/etudiants", headers=admin()).json()
    assert liste["total"] == 0


@pytest.mark.parametrize("role", ["ETUDIANT", "ENSEIGNANT"])
def test_acces_reserve_a_l_administrateur(env, role):
    """R10 : un jeton étudiant ou enseignant sur /etudiants reçoit 403, journalisé."""
    r = env.client.get("/api/v1/etudiants", headers=entetes(role))
    assert r.status_code == 403
    assert evenements(env)[-1]["action"] == "ACCES_REFUSE"


def test_pagination_limitee_a_50(env):
    """R11."""
    r = env.client.get("/api/v1/etudiants?taille=500", headers=admin())
    assert r.status_code == 422


def test_modification_tracee_avec_avant_apres(env):
    e = ajouter(env).json()
    r = env.client.patch(f"/api/v1/etudiants/{e['id']}", headers=admin(), json={"prenom": "Aminatou", "version": e["version"]})
    assert r.status_code == 200
    ev = evenements(env)[-1]
    assert ev["action"] == "ETUDIANT_MODIFIE"
    assert ev["details"] == {"avant": {"prenom": "Aminata"}, "apres": {"prenom": "Aminatou"}}


def test_modification_sur_version_perimee_refusee(env):
    e = ajouter(env).json()
    env.client.patch(f"/api/v1/etudiants/{e['id']}", headers=admin(), json={"prenom": "Aminatou", "version": 1})
    r = env.client.patch(f"/api/v1/etudiants/{e['id']}", headers=admin(), json={"prenom": "Ami", "version": 1})
    assert r.status_code == 409


def test_matricule_non_modifiable(env):
    e = ajouter(env).json()
    r = env.client.patch(f"/api/v1/etudiants/{e['id']}", headers=admin(), json={"matricule": "ETU-2026-0999", "version": 1})
    assert r.status_code == 422


def test_archivage_exige_le_matricule_et_desactive_le_compte(env):
    """R13 : archivage logique, double confirmation, aucune route DELETE."""
    e = ajouter(env).json()
    mauvais = env.client.post(f"/api/v1/etudiants/{e['id']}/archivage", headers=admin(),
                              json={"confirmation_matricule": "ETU-2000-0000", "version": e["version"]})
    assert mauvais.status_code == 422
    r = env.client.post(f"/api/v1/etudiants/{e['id']}/archivage", headers=admin(),
                        json={"confirmation_matricule": e["matricule"], "version": e["version"]})
    assert r.status_code == 200 and r.json()["statut"] == "ARCHIVE"
    assert any(a[0] == "PATCH" and a[1].endswith("/statut") and a[2] == {"statut": "DESACTIVE"} for a in env.auth.appels)
    assert env.client.delete(f"/api/v1/etudiants/{e['id']}", headers=admin()).status_code == 405
    # La fiche reste consultable.
    assert env.client.get(f"/api/v1/etudiants/{e['id']}", headers=admin()).status_code == 200


def test_routes_internes_exigent_le_jeton_du_service_notes(env):
    e = ajouter(env).json()
    assert env.client.get(f"/internal/etudiants/{e['id']}").status_code == 401
    assert env.client.get(f"/internal/etudiants/{e['id']}", headers=entete_service("service_token_etudiants")).status_code == 401
    ok = env.client.get(f"/internal/etudiants/{e['id']}", headers=entete_service("service_token_notes"))
    assert ok.status_code == 200 and set(ok.json()) == {"id", "matricule", "nom", "prenom", "statut"}


def test_us10_changement_d_email_reporte_sur_le_compte(env):
    e = ajouter(env).json()
    r = env.client.patch(f"/api/v1/etudiants/{e['id']}", headers=admin(),
                         json={"email": "aminata.diallo@etu.univ-exemple.cm", "version": e["version"]})
    assert r.status_code == 200
    appel = [a for a in env.auth.appels if a[0] == "PATCH" and a[1].endswith("/email")]
    assert appel and appel[0][2] == {"email": "aminata.diallo@etu.univ-exemple.cm"}


def test_jeton_revoque_refuse_immediatement(env):
    """US06, US11 : un jeton émis avant la révocation du compte est refusé (401)."""
    import time
    import uuid
    sub = uuid.uuid4()
    entete = entetes("ADMINISTRATEUR", sub=sub)
    assert env.client.get("/api/v1/etudiants", headers=entete).status_code == 200
    env.client.app.state.revocations.ajouter(str(sub), int(time.time() * 1000) + 1000)
    r = env.client.get("/api/v1/etudiants", headers=entete)
    assert r.status_code == 401 and r.json()["erreur"]["code"] == "SESSION_REVOQUEE"
