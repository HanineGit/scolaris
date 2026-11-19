"""Test de bout en bout sur la pile Docker démarrée (docker compose up -d).

Rejoue le parcours complet à travers la passerelle HTTPS, comme le feraient
les interfaces : activation, second facteur, saisie, modification, consultation
mobile et audit. Les e-mails d'activation sont lus dans Mailpit.

Usage : python scripts/test_bout_en_bout.py
"""
import os
import re
import secrets
import sys
import time
import uuid

import httpx
import pyotp

URL = os.environ.get("SCOLARIS_URL", "https://localhost:9443")
API = f"{URL}/api/v1"
MAILPIT = f"http://127.0.0.1:{os.environ.get('MAILPIT_PORT', '8026')}/api/v1"
# Jamais de mot de passe écrit dans le code : variable du pipeline ou valeur aléatoire.
MDP = os.environ.get("SCOLARIS_MDP_TEST") or f"Sc-{secrets.token_urlsafe(12)}9a!"
# Certificat auto-signé de développement : vérification désactivée pour ce script local uniquement.
client = httpx.Client(verify=False, timeout=15)  # nosec B501
etapes = 0


def ok(condition: bool, message: str):
    global etapes
    if not condition:
        print(f"ÉCHEC : {message}")
        sys.exit(1)
    etapes += 1
    print(f"  ok  {message}")


def dernier_lien(destinataire: str) -> str:
    for _ in range(20):
        messages = httpx.get(f"{MAILPIT}/search", params={"query": f"to:{destinataire}"}).json()["messages"]
        if messages:
            texte = httpx.get(f"{MAILPIT}/message/{messages[0]['ID']}").json()["Text"]
            return re.search(r"#jeton=([A-Za-z0-9_\-]+)", texte).group(1)
        time.sleep(0.5)
    raise RuntimeError(f"Aucun e-mail pour {destinataire}")


def activer_personnel(email: str) -> str:
    jeton = dernier_lien(email)
    prep = client.post(f"{API}/auth/activation/verifier", json={"jeton": jeton}).json()
    secret = pyotp.parse_uri(prep["mfa_uri"]).secret
    r = client.post(f"{API}/auth/activation", json={"jeton": jeton, "mot_de_passe": MDP, "confirmation": MDP,
                                                    "code_totp": pyotp.TOTP(secret).now()})
    ok(r.status_code == 204, f"activation du compte {email} avec second facteur")
    return secret


def connecter_personnel(email: str, secret: str) -> dict:
    r = client.post(f"{API}/auth/connexion", json={"identifiant": email, "mot_de_passe": MDP})
    ok(r.json().get("mfa_requis") is True, f"{email} : mot de passe accepté, code TOTP exigé")
    time.sleep(31 - time.time() % 30)  # nouveau pas TOTP : le code d'activation ne peut pas être rejoué
    r = client.post(f"{API}/auth/mfa/verifier", json={"jeton_mfa": r.json()["jeton_mfa"], "code": pyotp.TOTP(secret).now()})
    ok(r.status_code == 200, f"{email} : connexion complète")
    return {"Authorization": f"Bearer {r.json()['jeton_acces']}"}


print("1. Passerelle")
r = httpx.get(f"http://localhost:{os.environ.get('PORT_HTTP', '9080')}/", follow_redirects=False)
ok(r.status_code == 301 and r.headers["location"].startswith("https://"), "HTTP redirigé vers HTTPS")
r = client.get(f"{URL}/")
ok("Strict-Transport-Security" in r.headers and r.headers.get("Server") == "nginx", "HSTS présent, version de Nginx masquée")
ok(client.get(f"{URL}/internal/comptes").status_code == 404, "routes internes inaccessibles")

print("2. Administrateur initial")
secret_admin = activer_personnel("admin@univ-exemple.cm")
admin = connecter_personnel("admin@univ-exemple.cm", secret_admin)

def attendre(condition, delai=20):
    """Les événements transitent par le bus : on attend leur arrivée sans dépasser le délai."""
    fin = time.time() + delai
    while time.time() < fin:
        resultat = condition()
        if resultat:
            return resultat
        time.sleep(1)
    return None


print("3. Calendrier, classe, matière, affectation")
suffixe = uuid.uuid4().hex[:6]
annee = time.strftime("%Y") if int(time.strftime("%m")) >= 9 else str(int(time.strftime("%Y")) - 1)
annee = f"{annee}-{int(annee) + 1}"
r = client.post(f"{API}/classes", headers=admin, json={"code": f"L2-{suffixe[:4].upper()}", "libelle": "Licence 2 Informatique",
                                                       "filiere": "Informatique", "niveau": "L2", "annee_academique": annee})
ok(r.status_code == 201, "classe créée")
classe = r.json()["id"]
semestres = client.get(f"{API}/semestres", headers=admin).json()["elements"]
semestre = next((x for x in semestres if x["numero"] == 1), None) or client.post(
    f"{API}/semestres", headers=admin, json={"annee_academique": annee, "numero": 1}).json()
jour = time.strftime("%Y-%m-%d")
r = client.put(f"{API}/semestres/{semestre['id']}/fenetre", headers=admin,
               json={"saisie_debut": jour, "saisie_fin": jour})
ok(r.status_code == 200 and r.json()["saisie_ouverte"], "fenêtre de saisie ouverte pour le semestre")
email_prof = f"prof.{suffixe}@univ-exemple.cm"
r = client.post(f"{API}/admin/comptes", headers=admin, json={"nom": "Abena", "prenom": "Jean", "email": email_prof, "role": "ENSEIGNANT"})
ok(r.status_code == 201, "compte enseignant créé")
prof_id = r.json()["id"]
secret_prof = activer_personnel(email_prof)
code = "S" + suffixe[:5].upper()
r = client.post(f"{API}/matieres", headers=admin, json={"code": code, "libelle": "Sécurité logicielle", "coefficient": "3",
                                                        "classe_id": classe, "semestre_id": semestre["id"]})
ok(r.status_code == 201, "matière créée et rattachée à la classe et au semestre")
matiere = r.json()["id"]
ok(client.post(f"{API}/matieres/{matiere}/affectations", headers=admin, json={"enseignant_id": prof_id}).status_code == 201,
   "enseignant affecté à la matière")

print("4. Étudiant inscrit dans la classe")
email_etu = f"etu.{suffixe}@etu.univ-exemple.cm"
r = client.post(f"{API}/etudiants", headers=admin, json={"nom": "Diallo", "prenom": "Aminata", "email": email_etu, "classe_id": classe})
ok(r.status_code == 201 and r.json()["classe"], f"étudiant créé dans la classe, matricule {r.json().get('matricule')}")
etudiant, matricule = r.json()["id"], r.json()["matricule"]
jeton = dernier_lien(email_etu)
ok(client.post(f"{API}/auth/activation", json={"jeton": jeton, "mot_de_passe": MDP, "confirmation": MDP}).status_code == 204,
   "compte étudiant activé")

print("5. Saisie, publication, verrouillage")
prof = connecter_personnel(email_prof, secret_prof)
grille = client.get(f"{API}/matieres/{matiere}/grille", headers=prof, params={"type_evaluation": "EXAMEN", "date_evaluation": jour}).json()
ok([l["etudiant"]["matricule"] for l in grille["lignes"]] == [matricule], "grille de saisie de la classe")
r = client.post(f"{API}/matieres/{matiere}/evaluations", headers=prof, json={
    "type_evaluation": "EXAMEN", "date_evaluation": jour, "notes": [{"etudiant_id": etudiant, "valeur": "9.5"}]})
ok(r.status_code == 201, "évaluation saisie pour toute la classe")
note = client.get(f"{API}/matieres/{matiere}/notes", headers=prof).json()["elements"][0]
r = client.put(f"{API}/notes/{note['id']}", headers=prof, json={"valeur": "10", "motif": "Erreur de report question 4", "version": note["version"]})
ok(r.status_code == 200, "note modifiée avec motif avant publication")
ok(client.post(f"{API}/notes", headers=admin, json={"matiere_id": matiere, "etudiant_id": etudiant, "type_evaluation": "TP",
                                                    "date_evaluation": jour, "valeur": "20"}).status_code == 403,
   "l'administrateur ne peut pas saisir de note")
r = client.post(f"{API}/auth/connexion", json={"identifiant": matricule, "mot_de_passe": MDP})
etu = {"Authorization": f"Bearer {r.json()['jeton_acces']}"}
ok(client.get(f"{API}/etudiants/moi/notes", headers=etu).json()["notes"] == [], "note invisible de l'étudiant avant publication")
ok(client.post(f"{API}/matieres/{matiere}/publication", headers=admin).status_code == 200, "notes publiées par l'administration")
r = client.put(f"{API}/notes/{note['id']}", headers=prof, json={"valeur": "12", "motif": "Tentative après publication", "version": 2})
ok(r.status_code == 409 and r.json()["erreur"]["code"] == "NOTES_PUBLIEES", "matière verrouillée après publication")

print("6. Espace étudiant")
r = client.get(f"{API}/etudiants/moi/notes", headers=etu)
ok(r.status_code == 200 and r.json()["notes"][0]["valeur"] == "10.00" and r.json()["notes"][0]["modifiee_le"],
   "l'étudiant voit sa note publiée, signalée comme modifiée")
ok(client.get(f"{API}/etudiants", headers=etu).status_code == 403, "l'étudiant n'accède pas à la liste des étudiants")
ok(client.get(f"{API}/etudiants/moi/synthese", headers=etu).json()["moyenne_generale"] == "10.00", "synthèse : moyenne générale")
ok(attendre(lambda: client.get(f"{API}/notifications", headers=etu).json()["non_lues"] >= 1),
   "notification de publication reçue par l'étudiant (via le bus)")
r = client.post(f"{API}/etudiants/moi/reclamations", headers=etu,
                json={"note_id": note["id"], "motif": "L'exercice 3 n'a pas été pris en compte dans le total."})
ok(r.status_code == 201, "réclamation déposée")
reclamation = r.json()
ok(attendre(lambda: any(n["categorie"] == "RECLAMATION" for n in client.get(f"{API}/notifications", headers=prof).json()["elements"])),
   "l'enseignant est notifié de la réclamation")
r = client.put(f"{API}/reclamations/{reclamation['id']}", headers=prof, json={
    "decision": "ACCEPTEE", "reponse": "Exercice 3 recompté : 2 points ajoutés.", "nouvelle_valeur": "12", "version": reclamation["version"]})
ok(r.status_code == 200 and r.json()["note"]["valeur"] == "12.00", "réclamation acceptée : note corrigée")
ok(client.get(f"{API}/etudiants/moi/notes", headers=etu).json()["notes"][0]["valeur"] == "12.00", "l'étudiant voit la note corrigée")
r = client.get(f"{API}/etudiants/moi/releve", headers=etu)
ok(r.status_code == 200 and r.content.startswith(b"%PDF"), "relevé de notes PDF téléchargé")
code_releve = r.headers.get("x-code-verification", "")
ok(re.fullmatch(r"[0-9a-f]{32}", code_releve) is not None, "code de vérification remis avec le relevé")
v = httpx.get(f"{API}/verification/{code_releve}", verify=False).json()  # nosec B501 : certificat de développement
ok(v["valide"] and v["matricule"].endswith(matricule[-2:]) and "**" in v["matricule"], "relevé authentifié par la page publique")

print("7. Sécurité et délibération")
s = client.get(f"{API}/moi/securite", headers=etu).json()
ok(any(x["courante"] for x in s["sessions"]) and s["connexions"][0]["resultat"] == "SUCCES", "espace sécurité : sessions et historique")
d = client.get(f"{API}/classes/{classe}/deliberation", headers=admin).json()
ok(d["resultats"][0]["decision"] == "ADMIS" and d["resultats"][0]["rang"] == 1, "délibération : décision et rang")
ok(client.get(f"{API}/classes/{classe}/deliberation", headers=prof).status_code == 403, "délibération réservée à l'administration")

print("8. Audit")
time.sleep(4)  # le relais transmet les événements toutes les 2 secondes
r = client.get(f"{API}/audit/evenements", headers=admin, params={"taille": 50}).json()
actions = {e["action"] for e in r["elements"]}
attendues = {"NOTE_AJOUTEE", "NOTE_MODIFIEE", "ETUDIANT_AJOUTE", "AUTH_SUCCES", "ACCES_REFUSE", "CLASSE_CREEE",
             "NOTES_PUBLIEES", "RECLAMATION_SOUMISE", "RECLAMATION_TRAITEE", "RELEVE_EMIS"}
ok(attendues <= actions, f"événements reçus et chaînés ({r['total']} au total)")
r = client.post(f"{API}/audit/integrite/verification", headers=admin).json()
ok(r["integre"] is True, f"chaîne d'intégrité vérifiée sur {r['nombre']} événements")

print(f"\nParcours complet réussi : {etapes} vérifications.")
