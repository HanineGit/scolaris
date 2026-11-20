"""Mesures de performance des critères d'acceptation (US01, US09, US27).

    python scripts/test_performance.py

Prérequis : pile démarrée et parcours de bout en bout déjà joué (compte étudiant
ETU-2026-0001 actif, une matière créée).

- Jeu de données : 10 000 étudiants fictifs (domaine perf.univ-exemple.cm), dont
  200 ont 4 notes chacun ; insérés une seule fois, directement en base.
- US01 : 20 connexions étudiantes simultanées depuis 20 adresses IP ; 95 % en moins de 2 s.
- US09 : 30 recherches par nom ou matricule sur 10 000 étudiants ; 95 % en moins d'une seconde,
  50 résultats au plus par page.
- US27 : 200 utilisateurs simultanés répartis sur 20 conteneurs (10 par adresse IP,
  comme 20 sites différents), à travers la passerelle HTTPS et ses limites ;
  95 % des requêtes en moins de 300 ms, puis refus 429 au-delà du débit autorisé par compte.

Les jetons d'accès des utilisateurs fictifs sont signés avec la clé de développement
(secrets/jwt_private_key) : la mesure porte sur la consultation, pas sur l'activation des comptes.
"""
import json
import os
import secrets
import statistics
import subprocess  # nosec B404
import sys
import time
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

RACINE = Path(__file__).resolve().parents[1]
os.environ.setdefault("SCOLARIS_SECRETS_DIR", str(RACINE / "secrets"))
from scolaris_common.testing import jeton  # noqa: E402  (lit SCOLARIS_SECRETS_DIR à l'import)

API = "https://localhost:9443/api/v1"
# Jamais de mot de passe écrit dans le code : variable du pipeline ou valeur aléatoire.
MDP = os.environ.get("SCOLARIS_MDP_TEST") or f"Sc-{secrets.token_urlsafe(12)}9a!"
SITES, PAR_SITE, DUREE, PAUSE = 20, 10, 60, 1.0
# Certificat auto-signé de développement : vérification désactivée pour ce script local uniquement.
client = httpx.Client(verify=False, timeout=15)  # nosec B501
echecs = []


def sql(base: str, requete: str) -> str:
    # La requête passe par l'entrée standard : pas de limite de longueur de la ligne de commande.
    r = subprocess.run(["docker", "compose", "exec", "-T", "-u", "postgres", "postgres",  # nosec B603 B607
                        "psql", "-v", "ON_ERROR_STOP=1", "-d", base, "-tAq"],
                       cwd=RACINE, input=requete, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise SystemExit(f"Erreur SQL sur {base} : {r.stderr[:400]}")
    return r.stdout.strip()


def p95(valeurs: list[float]) -> float:
    return statistics.quantiles(valeurs, n=100)[94] if len(valeurs) > 1 else valeurs[0]


def verifier(condition: bool, message: str):
    print(f"  {'ok ' if condition else 'ÉCHEC'}  {message}")
    if os.environ.get("GITHUB_ACTIONS"):
        # Chaque mesure apparaît en annotation sur la page de l'exécution.
        print(f"::{'notice' if condition else 'warning'} title=Performance::{message}")
    if not condition:
        echecs.append(message)


def preparer_donnees() -> list[str]:
    if sql("etudiant_db", "select count(*) from etudiant where email like '%@perf.univ-exemple.cm'") != "10000":
        sql("etudiant_db", """
            insert into etudiant (id, matricule, nom, prenom, email, statut, cree_par, cree_le, modifie_le, version)
            select gen_random_uuid(), 'ETU-2025-' || lpad(i::text, 4, '0'),
                   (array['Nkoulou','Mbarga','Fotso','Tchoupo','Ndiaye','Owona','Kamga','Ebode'])[1 + i % 8] || i,
                   (array['Aminata','Paul','Grâce','Hervé','Mireille','Samuel'])[1 + i % 6],
                   'perf' || i || '@perf.univ-exemple.cm', 'ACTIF', gen_random_uuid(), now(), now(), 1
            from generate_series(0, 9999) i""")
    # Seules des valeurs validées comme UUID (lues en base) et des constantes entrent dans la requête.
    ids = [str(uuid.UUID(e)) for e in sql("etudiant_db", "select id from etudiant where email like "
                                          "'%@perf.univ-exemple.cm' order by matricule limit 200").split()]
    matiere = str(uuid.UUID(sql("notes_db", "select id from matiere order by code limit 1")))
    valeurs = ",".join(f"(gen_random_uuid(), '{e}', '{matiere}', {10 + i % 10}.5, '{t}', date '2026-10-{1 + j:02d}', "
                       f"gen_random_uuid(), 'perf', now(), 1)"
                       for i, e in enumerate(ids) for j, t in enumerate(("CONTROLE_CONTINU", "EXAMEN", "TP", "RATTRAPAGE")))
    sql("notes_db", "insert into note (id, etudiant_id, matiere_id, valeur, type_evaluation, date_evaluation, "  # nosec B608
                    f"saisie_par, saisie_par_identifiant, saisie_le, version) values {valeurs} on conflict do nothing")
    return ids


def lancer_site(numero: int, jetons: list[str], depart: float) -> dict:
    conf = {"cible": "https://gateway:8443", "duree": DUREE, "pause": PAUSE, "jetons": jetons, "depart": depart, "connexion_a": depart - 25 + numero,
            "connexion": {"identifiant": "ETU-2026-0001", "mot_de_passe": MDP}}
    r = subprocess.run(["docker", "run", "--rm", "--network", "scolaris_dmz", "-e", f"CHARGE={json.dumps(conf)}",  # nosec B603 B607
                        "-v", f"{RACINE / 'scripts'}:/mesure:ro", "--entrypoint", "python",
                        "scolaris-notes", "/mesure/charge_site.py"], capture_output=True, text=True, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("Jeu de données")
etudiants = preparer_donnees()
print(f"  10 000 étudiants, dont {len(etudiants)} avec 4 notes")

print("US09 : recherche d'un étudiant")
admin = {"Authorization": f"Bearer {jeton('ADMINISTRATEUR', identifiant='admin@univ-exemple.cm')}"}
durees = []
for i, q in enumerate(["nkoulou", "ETU-2025-0042", "grâce", "mbarga12", "owona", "ETU-2025-9", "kamga7"] * 4 + ["ebode", "paul"]):
    debut = time.perf_counter()
    r = client.get(f"{API}/etudiants", headers=admin, params={"q": q, "taille": 50})
    durees.append(time.perf_counter() - debut)
    assert r.status_code == 200, r.status_code
    assert len(r.json()["elements"]) <= 50
    time.sleep(0.25)  # sous la limite par compte de la passerelle
verifier(p95(durees) < 1.0, f"30 recherches sur 10 000 étudiants : p95 = {p95(durees) * 1000:.0f} ms (seuil 1 000 ms)")
verifier(client.get(f"{API}/etudiants", headers=admin, params={"taille": 51}).status_code == 422,
         "plus de 50 résultats par page refusés (422)")

print(f"US01 et US27 : {SITES * PAR_SITE} utilisateurs simultanés depuis {SITES} adresses IP pendant {DUREE} s")
jetons = [jeton("ETUDIANT", etudiant_id=uuid.UUID(e), identifiant=f"perf{i}", duree=timedelta(minutes=10))
          for i, e in enumerate(etudiants)]
with ThreadPoolExecutor(SITES) as pool:
    depart = time.time() + 30  # laisse aux 20 conteneurs le temps de démarrer et de se connecter
    sites = list(pool.map(lambda n: lancer_site(n, jetons[n * PAR_SITE:(n + 1) * PAR_SITE], depart), range(SITES)))
connexions = [s["connexion"]["duree"] for s in sites if s["connexion"]["code"] == 200]
verifier(len(connexions) == SITES and p95(connexions) < 2.0,
         f"US01 : {len(connexions)}/{SITES} connexions réussies, p95 = {p95(connexions) * 1000:.0f} ms (seuil 2 000 ms)")
toutes = [d for s in sites for d in s["durees"]]
codes: dict[str, int] = {}
for s in sites:
    for c, n in s["codes"].items():
        codes[c] = codes.get(c, 0) + n
instants = [t for s in sites for t in s["instants"]]
for debut_tranche in range(0, DUREE, 10):
    tranche = [d for d, t in zip(toutes, instants) if debut_tranche <= t < debut_tranche + 10]
    if len(tranche) > 1:
        print(f"  de {debut_tranche:2d} à {debut_tranche + 10:2d} s : {len(tranche):5d} requêtes, p95 {p95(tranche) * 1000:5.0f} ms")
print(f"  {len(toutes)} requêtes, codes {codes}, médiane {statistics.median(toutes) * 1000:.0f} ms, "
      f"maximum {max(toutes) * 1000:.0f} ms")
verifier(codes.get("200", 0) == len(toutes), "toutes les consultations ont abouti (200)")
verifier(p95(toutes) < 0.3, f"US27 : p95 = {p95(toutes) * 1000:.0f} ms (seuil 300 ms)")

print("US27 : limite par compte")
rafale = jeton("ETUDIANT", etudiant_id=uuid.UUID(etudiants[0]), identifiant="rafale")
codes_rafale = [client.get(f"{API}/etudiants/moi/notes", headers={"Authorization": f"Bearer {rafale}"}).status_code
                for _ in range(40)]
verifier(429 in codes_rafale, f"rafale de 40 requêtes d'un même compte : {codes_rafale.count(429)} refus 429")
autre = jeton("ETUDIANT", etudiant_id=uuid.UUID(etudiants[1]), identifiant="autre")
verifier(client.get(f"{API}/etudiants/moi/notes", headers={"Authorization": f"Bearer {autre}"}).status_code == 200,
         "un autre compte reste servi normalement")

if echecs:
    sys.exit(f"{len(echecs)} critère(s) non atteint(s).")
print("Tous les critères de performance sont atteints.")
