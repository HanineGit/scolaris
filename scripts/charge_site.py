"""Un « site » de la mesure de charge : lancé dans un conteneur, donc avec sa propre adresse IP.

Lit la configuration dans la variable CHARGE (JSON) :
  {"cible": ..., "duree": s, "pause": s, "jetons": [...], "connexion": {"identifiant": ..., "mot_de_passe": ...}}
Écrit les mesures sur la sortie standard (JSON). Appelé par scripts/test_performance.py.
"""
import json
import os
import random
import threading
import time

import httpx

conf = json.loads(os.environ["CHARGE"])
cible = conf["cible"]
# Certificat de développement émis pour « localhost » : vérification désactivée pour la mesure.
client = httpx.Client(verify=False, timeout=10, headers={"Host": "localhost:9443"},  # nosec B501
                      limits=httpx.Limits(max_connections=len(conf["jetons"]) + 2))
resultat = {"connexion": None, "durees": [], "instants": [], "codes": {}}
verrou = threading.Lock()

if conf.get("connexion"):
    # Connexions étalées : une par seconde sur l'ensemble des sites.
    time.sleep(max(0.0, conf.get("connexion_a", 0) - time.time()))
    debut = time.perf_counter()
    r = client.post(f"{cible}/api/v1/auth/connexion", json=conf["connexion"])
    resultat["connexion"] = {"duree": time.perf_counter() - debut, "code": r.status_code}

# Tous les sites démarrent la charge au même instant, une fois les connexions mesurées.
time.sleep(max(0.0, conf.get("depart", 0) - time.time()))


def utilisateur(jeton: str):
    entetes = {"Authorization": f"Bearer {jeton}"}
    fin = time.monotonic() + conf["duree"]
    # Arrivées désynchronisées : sans cela, les 200 utilisateurs resteraient en phase et
    # enverraient leurs requêtes dans la même milliseconde à chaque seconde.
    time.sleep(random.uniform(0, conf["pause"]))  # nosec B311 : simple répartition de la charge
    while time.monotonic() < fin:
        debut = time.perf_counter()
        try:
            code = client.get(f"{cible}/api/v1/etudiants/moi/notes", headers=entetes).status_code
        except httpx.HTTPError:
            code = 0
        duree = time.perf_counter() - debut
        with verrou:
            resultat["durees"].append(duree)
            resultat["instants"].append(time.time() - conf.get("depart", 0))
            resultat["codes"][str(code)] = resultat["codes"].get(str(code), 0) + 1
        time.sleep(random.uniform(0.5, 1.5) * conf["pause"])  # nosec B311 : 1 requête par seconde en moyenne


fils = [threading.Thread(target=utilisateur, args=(j,)) for j in conf["jetons"]]
for f in fils:
    f.start()
for f in fils:
    f.join()
print(json.dumps(resultat))
