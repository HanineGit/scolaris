"""Moindre privilège en base, vérifié sur la pile démarrée (US17, US18, US23, US24, risque R25).

    python scripts/verifier_privileges.py

Chaque compte de service n'accède qu'à sa base, l'historique des notes et le
journal d'audit ne peuvent être ni modifiés ni supprimés, et toute connexion
PostgreSQL non chiffrée est rejetée.
"""
import subprocess  # nosec B404
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
INTERDITS = [
    ("notes_db", "svc_notes_rw", "update historique_note set motif = motif", "modification de l'historique des notes"),
    ("notes_db", "svc_notes_rw", "delete from historique_note", "suppression de l'historique des notes"),
    ("notes_db", "svc_notes_rw", "delete from note", "suppression d'une note"),
    ("notes_db", "svc_notes_ro", "update note set valeur = valeur", "écriture par le compte en lecture seule"),
    ("audit_db", "svc_audit", "update evenement_audit set action = action", "modification du journal d'audit"),
    ("audit_db", "svc_audit", "delete from evenement_audit", "suppression du journal d'audit"),
    ("notifications_db", "svc_notifications", "delete from notification", "suppression d'une notification"),
    ("notes_db", "svc_notes_ro", "select 1 from releve_emis limit 1", "lecture des relevés émis par le compte en lecture seule"),
]
BASES = {"svc_auth": "auth_db", "svc_etudiant": "etudiant_db", "svc_notes_rw": "notes_db",
         "svc_notes_ro": "notes_db", "svc_audit": "audit_db", "svc_notifications": "notifications_db"}


def psql(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", "exec", "-T", "-u", "postgres", "postgres", "psql", "-tA", *args],  # nosec B603 B607
                          cwd=RACINE, capture_output=True, text=True, check=False)


echecs = 0
for base, role, requete, libelle in INTERDITS:
    r = psql("-d", base, "-c", f"set role {role}", "-c", requete)
    refuse = "permission denied" in r.stderr
    print(f"  {'ok ' if refuse else 'ÉCHEC'}  {libelle} refusée ({role})")
    echecs += not refuse

r = psql("-c", "select r.rolname || '=' || string_agg(d.datname, ',' order by d.datname) from pg_roles r, pg_database d "
               "where r.rolname like 'svc%' and d.datname like '%_db' "
               "and has_database_privilege(r.rolname, d.datname, 'CONNECT') group by r.rolname")
acces = dict(ligne.split("=") for ligne in r.stdout.split())
for role, base in BASES.items():
    seul = acces.get(role) == base
    print(f"  {'ok ' if seul else 'ÉCHEC'}  {role} n'accède qu'à {base} (accès : {acces.get(role)})")
    echecs += not seul

r = subprocess.run(["docker", "compose", "exec", "-T", "-u", "postgres", "postgres", "sh", "-c",  # nosec B603 B607
                    "PGPASSWORD=x psql 'host=127.0.0.1 user=svc_auth dbname=auth_db sslmode=disable' -c 'select 1'"],
                   cwd=RACINE, capture_output=True, text=True, check=False)
rejete = "no encryption" in r.stderr
print(f"  {'ok ' if rejete else 'ÉCHEC'}  connexion PostgreSQL sans chiffrement rejetée")
echecs += not rejete

sys.exit(f"{echecs} contrôle(s) en échec." if echecs else 0)
