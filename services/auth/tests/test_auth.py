"""Tests de sécurité du service Authentification.

Chaque test reprend un critère de succès du tableau des réponses aux risques.
"""
import secrets

import httpx
import pyotp
import pytest
from scolaris_common import revocation
from scolaris_common.config import lire_secret

from conftest import evenements, jeton_du_dernier_mail

MDP = f"Sc-{secrets.token_urlsafe(12)}9a!"
JETON_SERVICE = lambda: {"X-Service-Token": lire_secret("service_token_etudiants")}  # noqa: E731


def creer_etudiant(env, matricule="ETU-2026-0142", email="a.diallo@etu.univ-exemple.cm"):
    import uuid
    r = env.client.post("/internal/comptes/etudiants", headers=JETON_SERVICE(),
                        json={"etudiant_id": str(uuid.uuid4()), "matricule": matricule, "email": email})
    assert r.status_code == 201, r.text
    return jeton_du_dernier_mail(env.expediteur)


def activer_etudiant(env, matricule="ETU-2026-0142", email="a.diallo@etu.univ-exemple.cm"):
    jeton = creer_etudiant(env, matricule, email)
    r = env.client.post("/api/v1/auth/activation", json={"jeton": jeton, "mot_de_passe": MDP, "confirmation": MDP})
    assert r.status_code == 204, r.text


def creer_admin(env, email="admin@univ-exemple.cm"):
    """Crée un administrateur actif directement en base et retourne son secret TOTP."""
    from app import crypto, passwords
    from app.models import Utilisateur
    secret = pyotp.random_base32()
    with env.db.fabrique()() as s:
        u = Utilisateur(identifiant=email.split("@")[0], email=email, nom="ADMIN", prenom="Test",
                        role="ADMINISTRATEUR", statut="ACTIF", hash_mot_de_passe=passwords.hacher(MDP))
        s.add(u)
        s.flush()
        u.secret_mfa_chiffre = crypto.chiffrer(secret, u.id.bytes)
        s.commit()
    return secret


def connecter_admin(env, secret, email="admin@univ-exemple.cm"):
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": email, "mot_de_passe": MDP})
    assert r.status_code == 200 and r.json()["mfa_requis"], r.text
    r = env.client.post("/api/v1/auth/mfa/verifier", json={"jeton_mfa": r.json()["jeton_mfa"], "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['jeton_acces']}"}


# --- F01 : connexion ---

def test_connexion_etudiant_reussie(env):
    activer_etudiant(env)
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": MDP})
    assert r.status_code == 200
    corps = r.json()
    assert corps["utilisateur"]["role"] == "ETUDIANT"
    assert corps["jeton_acces"] and corps["jeton_rafraichissement"]
    assert "AUTH_SUCCES" in evenements(env)


def test_message_identique_compte_existant_ou_non(env):
    """R03 : la réponse ne révèle pas si le compte existe."""
    activer_etudiant(env)
    a = env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": "faux"})
    b = env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2099-9999", "mot_de_passe": "faux"})
    assert a.status_code == b.status_code == 401
    assert a.json()["erreur"]["message"] == b.json()["erreur"]["message"] == "Identifiants invalides."


def test_verrouillage_apres_cinq_echecs(env):
    """R01 : au 6e essai, même avec le bon mot de passe, le compte est verrouillé."""
    activer_etudiant(env)
    for _ in range(5):
        env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": "mauvais"})
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": MDP})
    assert r.status_code == 401
    assert "COMPTE_VERROUILLE" in evenements(env)


def test_personnel_ne_peut_pas_se_connecter_sans_totp(env):
    """R01 : le mot de passe seul ne donne aucun jeton d'accès au personnel."""
    creer_admin(env)
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "admin@univ-exemple.cm", "mot_de_passe": MDP})
    assert r.status_code == 200
    assert set(r.json()) == {"mfa_requis", "jeton_mfa"}
    # Le jeton intermédiaire n'ouvre pas l'API.
    r2 = env.client.get("/api/v1/admin/comptes", headers={"Authorization": f"Bearer {r.json()['jeton_mfa']}"})
    assert r2.status_code == 401


def test_code_totp_ne_peut_pas_etre_rejoue(env):
    secret = creer_admin(env)
    code = pyotp.TOTP(secret).now()
    for attendu in (200, 401):
        r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "admin@univ-exemple.cm", "mot_de_passe": MDP})
        r = env.client.post("/api/v1/auth/mfa/verifier", json={"jeton_mfa": r.json()["jeton_mfa"], "code": code})
        assert r.status_code == attendu


# --- F01 : session ---

def test_rotation_et_detection_de_reutilisation(env):
    """R02 : un jeton de rafraichissement réutilisé révoque toute la session."""
    activer_etudiant(env)
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": MDP})
    premier = r.json()["jeton_rafraichissement"]
    second = env.client.post("/api/v1/auth/rafraichir", json={"jeton_rafraichissement": premier}).json()["jeton_rafraichissement"]
    assert env.client.post("/api/v1/auth/rafraichir", json={"jeton_rafraichissement": premier}).status_code == 401
    # Le jeton légitime suivant est lui aussi révoqué.
    assert env.client.post("/api/v1/auth/rafraichir", json={"jeton_rafraichissement": second}).status_code == 401
    assert "SESSION_REVOQUEE" in evenements(env)


def test_jeton_falsifie_refuse(env):
    import jwt
    faux = jwt.encode({"sub": "x", "role": "ADMINISTRATEUR", "typ": "access"}, "secret", algorithm="HS256")
    r = env.client.get("/api/v1/admin/comptes", headers={"Authorization": f"Bearer {faux}"})
    assert r.status_code == 401


# --- F02 : activation ---

def test_lien_activation_a_usage_unique(env):
    """R04."""
    jeton = creer_etudiant(env)
    corps = {"jeton": jeton, "mot_de_passe": MDP, "confirmation": MDP}
    assert env.client.post("/api/v1/auth/activation", json=corps).status_code == 204
    assert env.client.post("/api/v1/auth/activation", json=corps).status_code == 400


@pytest.mark.parametrize("mdp", ["court1!A", "sanschiffre-ABC!", "SansSpecial1234", "Azerty@12345"])
def test_politique_mot_de_passe(env, mdp):
    """R05 : tout mot de passe non conforme est refusé."""
    jeton = creer_etudiant(env)
    r = env.client.post("/api/v1/auth/activation", json={"jeton": jeton, "mot_de_passe": mdp, "confirmation": mdp})
    assert r.status_code == 422


def test_activation_personnel_exige_le_second_facteur(env):
    secret_admin = creer_admin(env)
    entetes = connecter_admin(env, secret_admin)
    r = env.client.post("/api/v1/admin/comptes", headers=entetes,
                        json={"nom": "Abena", "prenom": "Jean", "email": "j.abena@univ-exemple.cm", "role": "ENSEIGNANT"})
    assert r.status_code == 201
    jeton = jeton_du_dernier_mail(env.expediteur)
    prep = env.client.post("/api/v1/auth/activation/verifier", json={"jeton": jeton}).json()
    assert prep["mfa_requis"] and prep["mfa_uri"].startswith("otpauth://")
    sans_code = env.client.post("/api/v1/auth/activation", json={"jeton": jeton, "mot_de_passe": MDP, "confirmation": MDP})
    assert sans_code.status_code == 422
    secret = pyotp.parse_uri(prep["mfa_uri"]).secret
    ok = env.client.post("/api/v1/auth/activation", json={"jeton": jeton, "mot_de_passe": MDP, "confirmation": MDP,
                                                          "code_totp": pyotp.TOTP(secret).now()})
    assert ok.status_code == 204


# --- F03 : comptes et rôles ---

def test_etudiant_ne_peut_pas_gerer_les_comptes(env):
    """R06 : un rôle non administrateur reçoit 403 et l'essai est journalisé."""
    activer_etudiant(env)
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": MDP})
    entetes = {"Authorization": f"Bearer {r.json()['jeton_acces']}"}
    assert env.client.get("/api/v1/admin/comptes", headers=entetes).status_code == 403
    assert "ACCES_REFUSE" in evenements(env)


def test_admin_ne_peut_pas_modifier_son_propre_role(env):
    secret = creer_admin(env)
    entetes = connecter_admin(env, secret)
    moi = env.client.get("/api/v1/admin/comptes", headers=entetes).json()["elements"][0]["id"]
    r = env.client.patch(f"/api/v1/admin/comptes/{moi}", headers=entetes, json={"role": "ENSEIGNANT"})
    assert r.status_code == 409


def test_route_interne_exige_le_jeton_de_service(env):
    import uuid
    r = env.client.post("/internal/comptes/etudiants",
                        json={"etudiant_id": str(uuid.uuid4()), "matricule": "ETU-2026-0001", "email": "x@etu.univ-exemple.cm"})
    assert r.status_code == 401


# --- Erreurs et journaux ---

def test_erreur_de_validation_ne_renvoie_pas_la_saisie(env):
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "ab", "mot_de_passe": "SecretTresVisible", "en_trop": 1})
    assert r.status_code == 422
    assert "SecretTresVisible" not in r.text
    assert r.headers["Cache-Control"] == "no-store"


def test_aucun_secret_dans_les_evenements_d_audit(env):
    """R24."""
    activer_etudiant(env)
    env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": MDP})
    from app.models import EvenementSortant
    with env.db.fabrique()() as s:
        contenu = str([e.contenu for e in s.query(EvenementSortant)])
    assert MDP not in contenu


# --- Critères d'acceptation complémentaires (backlog, section 1.9.5) ---

def test_us02_cinq_codes_errones_verrouillent_le_compte(env):
    secret = creer_admin(env)
    for _ in range(5):
        r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "admin@univ-exemple.cm", "mot_de_passe": MDP})
        env.client.post("/api/v1/auth/mfa/verifier", json={"jeton_mfa": r.json()["jeton_mfa"], "code": "000000"})
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "admin@univ-exemple.cm", "mot_de_passe": MDP})
    assert r.status_code == 401
    assert "COMPTE_VERROUILLE" in evenements(env)
    assert secret  # le bon code ne suffit plus pendant 15 minutes


def test_us02_etape_du_code_expire_apres_5_minutes(env):
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone

    import jwt
    creer_admin(env)
    t = datetime.now(timezone.utc) - timedelta(minutes=6)
    perime = jwt.encode({"iss": "scolaris-auth", "aud": "scolaris-api", "typ": "mfa", "sub": str(_uuid.uuid4()),
                         "iat": t, "exp": t + timedelta(minutes=5)}, lire_secret("jwt_private_key"), algorithm="RS256")
    r = env.client.post("/api/v1/auth/mfa/verifier", json={"jeton_mfa": perime, "code": "123456"})
    assert r.status_code == 401


def test_us03_session_inactive_15_minutes_refusee(env):
    from datetime import timedelta

    from app.models import JetonRafraichissement
    activer_etudiant(env)
    r = env.client.post("/api/v1/auth/connexion", json={"identifiant": "ETU-2026-0142", "mot_de_passe": MDP})
    with env.db.fabrique()() as s:
        for j in s.query(JetonRafraichissement):
            j.expire_le = j.expire_le - timedelta(minutes=16)
        s.commit()
    assert env.client.post("/api/v1/auth/rafraichir", json={"jeton_rafraichissement": r.json()["jeton_rafraichissement"]}).status_code == 401


def test_us04_lien_expire_apres_24_heures(env):
    from datetime import timedelta

    from app.models import JetonActivation
    jeton = creer_etudiant(env)
    with env.db.fabrique()() as s:
        for j in s.query(JetonActivation):
            j.expire_le = j.expire_le - timedelta(hours=24, seconds=1)
        s.commit()
    r = env.client.post("/api/v1/auth/activation", json={"jeton": jeton, "mot_de_passe": MDP, "confirmation": MDP})
    assert r.status_code == 400


def test_us05_creation_de_compte_journalisee(env):
    entetes = connecter_admin(env, creer_admin(env))
    env.client.post("/api/v1/admin/comptes", headers=entetes,
                    json={"nom": "Ngono", "prenom": "Marie", "email": "m.ngono@univ-exemple.cm", "role": "ENSEIGNANT"})
    assert "COMPTE_CREE" in evenements(env)


def _deux_admins(env):
    entetes_a = connecter_admin(env, creer_admin(env))
    secret_b = creer_admin(env, "second@univ-exemple.cm")
    entetes_b = connecter_admin(env, secret_b, "second@univ-exemple.cm")
    id_b = next(c["id"] for c in env.client.get("/api/v1/admin/comptes", headers=entetes_a).json()["elements"]
                if c["email"] == "second@univ-exemple.cm")
    return entetes_a, entetes_b, id_b


def test_us06_desactivation_refuse_immediatement_l_appel_suivant(env):
    """« Toutes ses sessions sont révoquées : son appel suivant reçoit un refus 401. »"""
    a, b, id_b = _deux_admins(env)
    assert env.client.get("/api/v1/admin/comptes", headers=b).status_code == 200
    assert env.client.patch(f"/api/v1/admin/comptes/{id_b}", headers=a, json={"statut": "DESACTIVE"}).status_code == 200
    r = env.client.get("/api/v1/admin/comptes", headers=b)
    assert r.status_code == 401 and r.json()["erreur"]["code"] == "SESSION_REVOQUEE"


def test_us05_changement_de_role_revoque_les_jetons(env):
    a, b, id_b = _deux_admins(env)
    env.client.patch(f"/api/v1/admin/comptes/{id_b}", headers=a, json={"role": "ENSEIGNANT"})
    assert env.client.get("/api/v1/admin/comptes", headers=b).status_code == 401


def test_us07_reinitialisation_du_second_facteur(env):
    a, b, id_b = _deux_admins(env)
    nb_mails = len(env.expediteur.envoyes)
    assert env.client.post(f"/api/v1/admin/comptes/{id_b}/mfa/reinitialiser", headers=a).status_code == 204
    assert len(env.expediteur.envoyes) == nb_mails + 1          # nouveau lien envoyé
    assert env.client.get("/api/v1/admin/comptes", headers=b).status_code == 401  # sessions révoquées
    assert "MFA_REINITIALISE" in evenements(env)


def test_resynchronisation_des_revocations_reservee_aux_services(env):
    a, b, id_b = _deux_admins(env)
    env.client.patch(f"/api/v1/admin/comptes/{id_b}", headers=a, json={"statut": "DESACTIVE"})
    assert env.client.get(revocation.CHEMIN_RESYNCHRONISATION).status_code == 401
    r = env.client.get(revocation.CHEMIN_RESYNCHRONISATION, headers={"X-Service-Token": lire_secret("service_token_audit")})
    assert r.status_code == 200 and r.json()[0]["utilisateur_id"] == id_b


def test_synchroniseur_des_autres_services_lit_la_route_d_auth(env, monkeypatch):
    """Contrat : la fonction utilisée par etudiants, notes et audit atteint bien la route d'auth."""
    a, b, id_b = _deux_admins(env)
    env.client.patch(f"/api/v1/admin/comptes/{id_b}", headers=a, json={"statut": "DESACTIVE"})
    monkeypatch.setattr(httpx, "get", lambda url, **kw: env.client.get(url.removeprefix("http://auth:8000"), **kw))
    lues = revocation.synchroniseur_http("http://auth:8000", "service_token_notes")()
    assert [u for u, _ in lues] == [id_b]
