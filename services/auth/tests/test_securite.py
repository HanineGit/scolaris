"""Tests de l'espace sécurité (F27) : sessions par appareil, historique, mot de passe, alertes."""
import secrets

from conftest import evenements, notifications
from test_auth import MDP, activer_etudiant, connecter_admin, creer_admin

NOUVEAU = f"Sc-{secrets.token_urlsafe(12)}9a!"
FAUX = f"Sc-{secrets.token_urlsafe(12)}9a!"
EDGE = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36 Edg/131.0"}
ANDROID = {"User-Agent": "okhttp/4.12.0 (Linux; Android 14)"}


def connecter(env, entetes=None, mdp=MDP):
    r = env.client.post("/api/v1/auth/connexion", headers=entetes or EDGE,
                        json={"identifiant": "ETU-2026-0142", "mot_de_passe": mdp})
    assert r.status_code == 200, r.text
    corps = r.json()
    return {"Authorization": f"Bearer {corps['jeton_acces']}"}, corps["jeton_rafraichissement"]


def test_sessions_par_appareil_et_session_courante(env):
    activer_etudiant(env)
    web, _ = connecter(env, EDGE)
    connecter(env, ANDROID)
    s = env.client.get("/api/v1/moi/securite", headers=web).json()
    appareils = {x["appareil"]: x["courante"] for x in s["sessions"]}
    assert appareils == {"Edge sous Windows": True, "Application Scolaris sous Android": False}
    assert [c["resultat"] for c in s["connexions"]] == ["SUCCES", "SUCCES"]
    assert "okhttp" not in str(s)  # la chaîne User-Agent brute n'est pas conservée


def test_fermer_la_session_d_un_appareil_perdu(env):
    activer_etudiant(env)
    web, _ = connecter(env, EDGE)
    _, rafraichissement_mobile = connecter(env, ANDROID)
    mobile = next(x for x in env.client.get("/api/v1/moi/securite", headers=web).json()["sessions"] if not x["courante"])
    assert env.client.delete(f"/api/v1/moi/sessions/{mobile['id']}", headers=web).status_code == 204
    assert env.client.post("/api/v1/auth/rafraichir", json={"jeton_rafraichissement": rafraichissement_mobile}).status_code == 401
    assert len(env.client.get("/api/v1/moi/securite", headers=web).json()["sessions"]) == 1
    assert "SESSION_FERMEE" in evenements(env)


def test_session_d_un_autre_compte_introuvable(env):
    activer_etudiant(env)
    web, _ = connecter(env)
    secret = creer_admin(env)
    admin = connecter_admin(env, secret)
    session_admin = env.client.get("/api/v1/moi/securite", headers=admin).json()["sessions"][0]["id"]
    assert env.client.delete(f"/api/v1/moi/sessions/{session_admin}", headers=web).status_code == 404


def test_fermeture_des_autres_sessions(env):
    activer_etudiant(env)
    web, _ = connecter(env, EDGE)
    connecter(env, ANDROID)
    connecter(env, ANDROID)
    assert env.client.post("/api/v1/moi/sessions/fermeture-des-autres", headers=web).json() == {"fermees": 2}
    assert [x["courante"] for x in env.client.get("/api/v1/moi/securite", headers=web).json()["sessions"]] == [True]


def test_changement_de_mot_de_passe(env):
    activer_etudiant(env)
    web, _ = connecter(env, EDGE)
    _, rafraichissement_mobile = connecter(env, ANDROID)
    faux = {"actuel": FAUX, "nouveau": NOUVEAU, "confirmation": NOUVEAU}
    assert env.client.put("/api/v1/moi/mot-de-passe", headers=web, json=faux).json()["erreur"]["code"] == "MDP_ACTUEL"
    faible = {"actuel": MDP, "nouveau": "motdepasse", "confirmation": "motdepasse"}
    assert env.client.put("/api/v1/moi/mot-de-passe", headers=web, json=faible).json()["erreur"]["code"] == "POLITIQUE_MDP"
    r = env.client.put("/api/v1/moi/mot-de-passe", headers=web, json={"actuel": MDP, "nouveau": NOUVEAU, "confirmation": NOUVEAU})
    assert r.status_code == 204
    assert env.client.post("/api/v1/auth/rafraichir", json={"jeton_rafraichissement": rafraichissement_mobile}).status_code == 401
    assert env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": MDP}).status_code == 401
    connecter(env, mdp=NOUVEAU)
    assert "MOT_DE_PASSE_MODIFIE" in evenements(env)
    assert any(n["titre"] == "Mot de passe modifié" for n in notifications(env))


def test_cinq_erreurs_sur_le_mot_de_passe_actuel_verrouillent(env):
    activer_etudiant(env)
    web, _ = connecter(env)
    faux = {"actuel": FAUX, "nouveau": NOUVEAU, "confirmation": NOUVEAU}
    for _ in range(5):
        env.client.put("/api/v1/moi/mot-de-passe", headers=web, json=faux)
    assert "COMPTE_VERROUILLE" in evenements(env)
    assert env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": MDP}).status_code == 401


def test_alerte_sur_nouvel_appareil_et_sur_verrouillage(env):
    activer_etudiant(env)
    connecter(env, EDGE)
    connecter(env, EDGE)
    assert notifications(env) == []  # appareil déjà connu
    connecter(env, ANDROID)
    alerte = notifications(env)[-1]
    assert alerte["categorie"] == "SECURITE" and "Application Scolaris sous Android" in alerte["message"]
    for _ in range(5):
        env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": FAUX})
    assert notifications(env)[-1]["titre"] == "Compte verrouillé"


def test_indicateurs_de_securite_reserves_a_l_administrateur(env):
    activer_etudiant(env)
    web, _ = connecter(env)
    env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": FAUX})
    admin = connecter_admin(env, creer_admin(env))
    i = env.client.get("/api/v1/admin/securite", headers=admin).json()
    assert i["connexions_24h"] == 2 and i["echecs_24h"] == 1 and i["comptes_actifs_par_role"]["ETUDIANT"] == 1
    assert env.client.get("/api/v1/admin/securite", headers=web).status_code == 403
