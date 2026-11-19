"""Jeu de démonstration réaliste sur une pile démarrée à neuf (jamais en production).

    SCOLARIS_URL=https://localhost:9543 MAILPIT_PORT=8027 python scripts/donnees_demo.py

Crée deux classes, deux semestres, deux enseignants, sept matières, trente étudiants
(import CSV), des notes saisies par grille, en publie une partie, active trois comptes
étudiants et dépose une réclamation. Les identifiants de démonstration sont écrits dans
rapports/demo_identifiants.txt (dossier non versionné).

Tout passe par l'API publique, avec les mêmes contrôles que l'interface : aucun accès
direct à la base.
"""
import os
import random
import re
import secrets
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pyotp

URL = os.environ.get("SCOLARIS_URL", "https://localhost:9543")
API = f"{URL}/api/v1"
MAILPIT = f"http://127.0.0.1:{os.environ.get('MAILPIT_PORT', '8027')}/api/v1"
# Mot de passe de démonstration tiré au hasard, écrit seulement dans rapports/ (non versionné).
MDP = f"Sc-{secrets.token_urlsafe(12)}9a!"
# Certificat auto-signé de développement : vérification désactivée pour ce script local uniquement.
client = httpx.Client(verify=False, timeout=30)  # nosec B501
alea = random.Random(2026)  # nosec B311 : valeurs de démonstration reproductibles
SORTIE = Path(__file__).resolve().parents[1] / "rapports" / "demo_identifiants.txt"

NOMS = ["NGONO", "MBARGA", "FOTSO", "TCHOUPO", "NDIAYE", "OWONA", "KAMGA", "EBODE", "ESSOMBA", "NJOYA", "ATANGANA", "BELLO",
        "DJOMO", "NANA", "MOUSSA", "ZE", "ABENA", "BIYA", "ONANA", "TAMO", "KENFACK", "NKOULOU", "MVONDO", "SIMO", "DOUALA",
        "YOMBI", "AWONO", "MEKA", "NGUELE", "ETOA"]
PRENOMS = ["Aminata", "Paul", "Grâce", "Hervé", "Mireille", "Samuel", "Clarisse", "Junior", "Brenda", "Arnaud", "Sandrine",
           "Yannick", "Laure", "Christian", "Estelle", "Boris", "Nadège", "Franck", "Carine", "Steve", "Inès", "Gaël",
           "Ruth", "Patrick", "Joëlle", "Kevin", "Diane", "Marius", "Flore", "Ulrich"]


def lien_activation(email: str) -> str:
    for _ in range(40):
        messages = httpx.get(f"{MAILPIT}/search", params={"query": f"to:{email}"}).json()["messages"]
        if messages:
            texte = httpx.get(f"{MAILPIT}/message/{messages[0]['ID']}").json()["Text"]
            return re.search(r"#jeton=([A-Za-z0-9_\-]+)", texte).group(1)
        time.sleep(0.5)
    raise RuntimeError(f"Aucun e-mail pour {email}")


def verifier(r: httpx.Response, attendu: int = 200):
    if r.status_code != attendu:
        raise SystemExit(f"Échec {r.request.method} {r.request.url.path} : {r.status_code} {r.text[:300]}")
    return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None


def activer_personnel(email: str) -> str:
    jeton = lien_activation(email)
    secret = pyotp.parse_uri(verifier(client.post(f"{API}/auth/activation/verifier", json={"jeton": jeton}))["mfa_uri"]).secret
    verifier(client.post(f"{API}/auth/activation", json={"jeton": jeton, "mot_de_passe": MDP, "confirmation": MDP,
                                                         "code_totp": pyotp.TOTP(secret).now()}), 204)
    return secret


def connecter_personnel(email: str, secret: str) -> dict:
    etape = verifier(client.post(f"{API}/auth/connexion", json={"identifiant": email, "mot_de_passe": MDP}))
    time.sleep(31 - time.time() % 30)  # nouveau pas TOTP : un code ne sert qu'une fois
    jetons = verifier(client.post(f"{API}/auth/mfa/verifier", json={"jeton_mfa": etape["jeton_mfa"], "code": pyotp.TOTP(secret).now()}))
    return {"Authorization": f"Bearer {jetons['jeton_acces']}"}


def note_vraisemblable(niveau: float) -> str:
    return f"{max(0, min(20, round(alea.gauss(niveau, 3.2) * 4) / 4)):.2f}"


print("Administrateur initial")
secret_admin = activer_personnel("admin@univ-exemple.cm")
admin = connecter_personnel("admin@univ-exemple.cm", secret_admin)

aujourd = date.today()
annee_debut = aujourd.year if aujourd.month >= 9 else aujourd.year - 1
annee = f"{annee_debut}-{annee_debut + 1}"

print("Calendrier")
s1 = verifier(client.post(f"{API}/semestres", headers=admin, json={
    "annee_academique": annee, "numero": 1, "saisie_debut": (aujourd - timedelta(days=30)).isoformat(),
    "saisie_fin": (aujourd + timedelta(days=30)).isoformat()}), 201)
verifier(client.post(f"{API}/semestres", headers=admin, json={"annee_academique": annee, "numero": 2}), 201)

print("Classes")
classes = {}
for code, libelle, niveau in (("L2-INFO", "Licence 2 Informatique", "L2"), ("L3-INFO", "Licence 3 Informatique", "L3")):
    classes[code] = verifier(client.post(f"{API}/classes", headers=admin, json={
        "code": code, "libelle": libelle, "filiere": "Informatique", "niveau": niveau, "annee_academique": annee}), 201)["id"]

print("Enseignants")
enseignants = {}
for nom, prenom, email in (("ABENA", "Jean", "j.abena@univ-exemple.cm"), ("MBALLA", "Clarisse", "c.mballa@univ-exemple.cm")):
    enseignants[email] = verifier(client.post(f"{API}/admin/comptes", headers=admin, json={
        "nom": nom, "prenom": prenom, "email": email, "role": "ENSEIGNANT"}), 201)["id"]
secrets_prof = {email: activer_personnel(email) for email in enseignants}

print("Matières")
MATIERES = [("INF201", "Algorithmique avancée", "4", "L2-INFO", "j.abena@univ-exemple.cm", 12.5),
            ("INF202", "Bases de données", "3", "L2-INFO", "j.abena@univ-exemple.cm", 11.0),
            ("INF203", "Réseaux informatiques", "2", "L2-INFO", "c.mballa@univ-exemple.cm", 10.5),
            ("MAT201", "Mathématiques discrètes", "3", "L2-INFO", "c.mballa@univ-exemple.cm", 9.5),
            ("ANG201", "Anglais technique", "1", "L2-INFO", "c.mballa@univ-exemple.cm", 13.5),
            ("INF301", "Sécurité logicielle", "4", "L3-INFO", "j.abena@univ-exemple.cm", 12.0),
            ("INF302", "Génie logiciel", "3", "L3-INFO", "c.mballa@univ-exemple.cm", 13.0)]
ids_matieres = {}
for code, libelle, coef, classe, prof, _ in MATIERES:
    m = verifier(client.post(f"{API}/matieres", headers=admin, json={
        "code": code, "libelle": libelle, "coefficient": coef, "classe_id": classes[classe], "semestre_id": s1["id"]}), 201)
    ids_matieres[code] = m["id"]
    verifier(client.post(f"{API}/matieres/{m['id']}/affectations", headers=admin, json={"enseignant_id": enseignants[prof]}), 201)

print("Étudiants (import CSV)")
for classe, debut, nombre in (("L2-INFO", 0, 18), ("L3-INFO", 18, 12)):
    lignes = ["nom;prenom;email"] + [f"{NOMS[i]};{PRENOMS[i]};{PRENOMS[i].lower().replace('ë', 'e').replace('è', 'e').replace('é', 'e').replace('â', 'a').replace('ï', 'i')}.{NOMS[i].lower()}@etu.univ-exemple.cm"
                                     for i in range(debut, debut + nombre)]
    r = verifier(client.post(f"{API}/etudiants/import", headers=admin,
                             json={"contenu": "\n".join(lignes), "classe_id": classes[classe], "confirmer": True}))
    print(f"  {classe} : {r['importes']} étudiants importés")

print("Notes (saisie par grille)")
for email, secret in secrets_prof.items():
    prof = connecter_personnel(email, secret)
    for code, _, _, _, titulaire, niveau in MATIERES:
        if titulaire != email:
            continue
        for type_eval, recul in (("CONTROLE_CONTINU", 21), ("EXAMEN", 4)):
            jour = (aujourd - timedelta(days=recul)).isoformat()
            grille = verifier(client.get(f"{API}/matieres/{ids_matieres[code]}/grille", headers=prof,
                                         params={"type_evaluation": type_eval, "date_evaluation": jour}))
            niveaux = {l["etudiant"]["id"]: niveau + alea.uniform(-3, 3) for l in grille["lignes"]}
            verifier(client.post(f"{API}/matieres/{ids_matieres[code]}/evaluations", headers=prof, json={
                "type_evaluation": type_eval, "date_evaluation": jour,
                "notes": [{"etudiant_id": i, "valeur": note_vraisemblable(n)} for i, n in niveaux.items()]}), 201)
    enseignants[email] = prof

print("Publication")
for code in ("INF201", "INF202", "MAT201", "INF301"):
    verifier(client.post(f"{API}/matieres/{ids_matieres[code]}/publication", headers=admin))

print("Comptes étudiants activés")
liste = verifier(client.get(f"{API}/etudiants", headers=admin, params={"classe_id": classes["L2-INFO"], "taille": 3}))["elements"]
etudiants_demo = []
for e in liste:
    verifier(client.post(f"{API}/auth/activation", json={"jeton": lien_activation(e["email"]), "mot_de_passe": MDP, "confirmation": MDP}), 204)
    etudiants_demo.append(e["matricule"])

print("Réclamation")
jetons = verifier(client.post(f"{API}/auth/connexion", json={"identifiant": etudiants_demo[0], "mot_de_passe": MDP}))
etu = {"Authorization": f"Bearer {jetons['jeton_acces']}"}
note = next(n for n in verifier(client.get(f"{API}/etudiants/moi/notes", headers=etu))["notes"] if n["matiere_code"] == "INF202")
verifier(client.post(f"{API}/etudiants/moi/reclamations", headers=etu, json={
    "note_id": note["id"], "motif": "La question 4 de l'examen ne semble pas avoir été comptée dans le total."}), 201)

SORTIE.parent.mkdir(exist_ok=True)
SORTIE.write_text(f"""Démonstration Scolaris – {URL}
Mot de passe commun : {MDP}

Administrateur : admin@univ-exemple.cm
  clé TOTP (à ajouter dans l'application d'authentification) : {secret_admin}
Enseignants :
""" + "".join(f"  {e} – clé TOTP : {s}\n" for e, s in secrets_prof.items()) + f"""Étudiants (application mobile, sans second facteur) : {", ".join(etudiants_demo)}
""", encoding="utf-8")
print(f"\nDémonstration prête. Identifiants : {SORTIE}")
