"""Résistance du bus d'audit (US24, risque R26) : aucun événement perdu si RabbitMQ s'arrête.

    python scripts/test_resilience_bus.py [duree_arret_s]     # 600 s par défaut (critère : 10 minutes)

Le bus est arrêté, des événements sont produits pendant l'arrêt (tentatives de
connexion échouées, tracées par le service auth), puis le bus redémarre. La boîte
d'envoi transactionnelle doit alors relayer chaque événement : le service audit
doit en recevoir exactement autant, et la chaîne d'intégrité doit rester valide.
"""
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

import httpx

RACINE = Path(__file__).resolve().parents[1]
API = "https://localhost:9443/api/v1"
# Le certificat de la passerelle est auto-signé en développement.
client = httpx.Client(verify=False, timeout=15)  # nosec B501


def compose(*args: str) -> str:
    r = subprocess.run(["docker", "compose", *args], cwd=RACINE, capture_output=True, text=True, check=True)  # nosec B603 B607
    return r.stdout.strip()


def sql(base: str, requete: str) -> str:
    return compose("exec", "-T", "-u", "postgres", "postgres", "psql", "-d", base, "-tAc", requete)


def evenements_audit() -> int:
    return int(sql("audit_db", "select count(*) from evenement_audit where action = 'AUTH_ECHEC'"))


def en_attente() -> int:
    return int(sql("auth_db", "select count(*) from evenement_sortant where not envoye"))


def attendre(condition, delai: float) -> bool:
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(2)
    return False


duree = int(sys.argv[1]) if len(sys.argv) > 1 else 600
avant = evenements_audit()
compose("stop", "rabbitmq")
print(f"Bus arrêté pour {duree} s ; {avant} échecs de connexion déjà audités.")

produits = 0
debut = time.monotonic()
while time.monotonic() - debut < duree:
    # 3 tentatives par minute : sous la limite de la passerelle (5 par minute et par IP).
    if produits < 3 * (int(time.monotonic() - debut) // 60 + 1):
        r = client.post(f"{API}/auth/connexion", json={"identifiant": f"inconnu{produits}@univ-exemple.cm", "mot_de_passe": "Faux-mot-de-passe-1"})
        assert r.status_code == 401, r.status_code
        produits += 1
    time.sleep(5)

bloques = en_attente()
print(f"{produits} événements produits pendant l'arrêt, {bloques} conservés dans la boîte d'envoi.")
assert evenements_audit() == avant, "des événements sont arrivés alors que le bus était arrêté"

compose("start", "rabbitmq")
recus = attendre(lambda: evenements_audit() == avant + produits, 180)
print(f"Après redémarrage : {evenements_audit() - avant}/{produits} événements reçus par l'audit, {en_attente()} en attente.")
assert recus, "événements perdus"

# Chaînage intact : chaque événement référence l'empreinte du précédent.
ruptures = sql("audit_db", "select count(*) from evenement_audit e join evenement_audit p "
                           "on p.numero = e.numero - 1 where e.empreinte_precedente <> p.empreinte")
assert ruptures == "0", f"{ruptures} rupture(s) de chaîne"
print("Aucun événement perdu.")
