# Scolaris – gestion simplifiée des notes étudiantes

Mise en œuvre du dossier d'analyse et de conception sécurisées (SDLC sécurisé).

## Organisation

| Dossier | Contenu | Fonctionnalités | Tests |
|---|---|---|---|
| `libs/common` | Secrets, vérification des jetons et des rôles, erreurs génériques, journaux sans secret, boîte d'envoi d'audit | transverse | via les services |
| `services/auth` | Service Authentification | F01, F02, F03 | 18 |
| `services/etudiants` | Service Étudiants | F04, F05, F06 | 17 |
| `services/notes` | Service Notes | F07 à F11 | 24 |
| `services/audit` | Service Audit (chaîne SHA-256) | F12, F13 | 10 |
| `gateway` | Passerelle Nginx (TLS 1.3, limitation de débit, en-têtes) | F14 | bout en bout |
| `infra/postgres` | Comptes PostgreSQL à droits minimaux | — | — |
| `web` | Back-office React (enseignant, administrateur) | — | à faire |
| `mobile` | Application React Native (étudiant) | — | à faire |
| `.github/workflows` | Chaîne CI/CD | — | à construire ensemble |

## Démarrer la pile complète

```bash
python -m venv .venv
.venv/Scripts/pip install cryptography httpx pyotp
.venv/Scripts/python scripts/generer_secrets.py      # crée ./secrets (jamais versionné)
docker compose up -d --build
```

- Back-office et API : https://localhost:9443 (certificat auto-signé de développement)
- E-mails d'activation (Mailpit) : http://127.0.0.1:8026
- Le premier administrateur (`admin@univ-exemple.cm`) reçoit son lien d'activation dans Mailpit.

Test de bout en bout sur la pile démarrée :

```bash
.venv/Scripts/python scripts/test_bout_en_bout.py
```

## Tests unitaires et analyse statique

```bash
.venv/Scripts/pip install -r services/notes/requirements.txt pytest httpx argon2-cffi pyotp bandit -e libs/common
cd services/notes && ../../.venv/Scripts/python -m pytest
cd ../.. && .venv/Scripts/bandit -r services/*/app libs/common/scolaris_common
```

## Pile de démonstration et d'essai (séparée de la pile principale)

Une seconde pile, avec ses propres bases et d'autres ports, sert aux tests de bout en bout
et à la démonstration sans toucher aux comptes réels :

```bash
export PORT_HTTPS=9543 PORT_HTTP=9180 MAILPIT_PORT=8027
docker compose -p scolaris-essai up -d --no-build --wait
SCOLARIS_URL=https://localhost:9543 .venv/Scripts/python scripts/donnees_demo.py
```

Le jeu de démonstration (2 classes, 7 matières, 30 étudiants, notes, publication, réclamation)
écrit ses identifiants dans `rapports/demo_identifiants.txt` (non versionné).

## Vérification des critères d'acceptation

Sur la pile démarrée, après le test de bout en bout (`.venv/Scripts/pip install -e libs/common` au préalable) :

| Script | Critères |
|---|---|
| `scripts/verifier_privileges.py` | moindre privilège en base, PostgreSQL chiffré obligatoire |
| `scripts/test_performance.py` | US01, US09, US27 (200 utilisateurs depuis 20 adresses IP, limite 429) |
| `scripts/test_resilience_bus.py [secondes]` | US23 : aucun événement perdu pendant un arrêt du bus (600 s par défaut) |
| `scripts/sauvegarde.py sauvegarder` puis `restaurer <dossier>` | US27 : sauvegarde chiffrée, restauration mesurée |
| `scripts/test_interface.py` | parcours du back-office dans un navigateur (`NAVIGATEUR=chromium` sous Linux) |


## Chaîne DevSecOps

`.github/workflows/devsecops.yml` rejoue tous ces contrôles à chaque modification :
secrets (gitleaks), analyse statique (Bandit), dépendances (pip-audit, npm audit, audit-ci),
tests et couverture, analyse des images (Trivy), intégration complète avec analyse dynamique
(OWASP ZAP), puis livraison des images après approbation manuelle. Une étape en échec bloque la suite.

## Règles

- Aucun secret dans le code ni dans le dépôt : ils sont lus depuis `/run/secrets` (Docker secrets).
- Chaque route vérifie le rôle côté serveur ; les notes vérifient en plus l'affectation de l'enseignant.
- Toute action sensible produit un événement d'audit, sans mot de passe ni jeton.
- Les conteneurs tournent sans privilèges (utilisateur non root, système de fichiers en lecture seule).
