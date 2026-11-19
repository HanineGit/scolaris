#!/bin/bash
# Initialisation de PostgreSQL : quatre bases, un compte de migration et un
# compte par service, avec le strict minimum de droits (moindre privilège).
# Les mots de passe proviennent des secrets Docker, jamais de ce fichier.
set -euo pipefail

lire() { tr -d '\n' < "/run/secrets/$1"; }

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<SQL
CREATE ROLE scolaris_migration LOGIN PASSWORD '$(lire pg_migration_password)';
CREATE ROLE svc_auth           LOGIN PASSWORD '$(lire pg_svc_auth_password)';
CREATE ROLE svc_etudiant       LOGIN PASSWORD '$(lire pg_svc_etudiant_password)';
CREATE ROLE svc_notes_rw       LOGIN PASSWORD '$(lire pg_svc_notes_rw_password)';
CREATE ROLE svc_notes_ro       LOGIN PASSWORD '$(lire pg_svc_notes_ro_password)';
CREATE ROLE svc_audit          LOGIN PASSWORD '$(lire pg_svc_audit_password)';
CREATE ROLE svc_notifications  LOGIN PASSWORD '$(lire pg_svc_notifications_password)';

CREATE DATABASE auth_db     OWNER scolaris_migration;
CREATE DATABASE etudiant_db OWNER scolaris_migration;
CREATE DATABASE notes_db    OWNER scolaris_migration;
CREATE DATABASE audit_db    OWNER scolaris_migration;
CREATE DATABASE notifications_db OWNER scolaris_migration;

-- Personne ne se connecte à une base qui n'est pas la sienne.
REVOKE ALL ON DATABASE auth_db, etudiant_db, notes_db, audit_db, notifications_db FROM PUBLIC;
GRANT CONNECT ON DATABASE auth_db     TO svc_auth;
GRANT CONNECT ON DATABASE etudiant_db TO svc_etudiant;
GRANT CONNECT ON DATABASE notes_db    TO svc_notes_rw, svc_notes_ro;
GRANT CONNECT ON DATABASE audit_db    TO svc_audit;
GRANT CONNECT ON DATABASE notifications_db TO svc_notifications;
SQL

# Droits par défaut sur les tables que le compte de migration créera ensuite.
droits() {
  local base=$1; shift
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$base" <<SQL
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO scolaris_migration;
$*
SQL
}

# Authentification et Étudiants : lecture, ajout, mise à jour ; jamais de suppression.
droits auth_db "GRANT USAGE ON SCHEMA public TO svc_auth;
ALTER DEFAULT PRIVILEGES FOR ROLE scolaris_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO svc_auth;"

droits etudiant_db "GRANT USAGE ON SCHEMA public TO svc_etudiant;
ALTER DEFAULT PRIVILEGES FOR ROLE scolaris_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO svc_etudiant;"

# Notes : lecture-écriture pour les enseignants, lecture seule pour la consultation mobile.
# Les droits fins (historique sans UPDATE, DELETE sur affectation) sont posés par la migration.
droits notes_db "GRANT USAGE ON SCHEMA public TO svc_notes_rw, svc_notes_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE scolaris_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO svc_notes_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE scolaris_migration IN SCHEMA public GRANT SELECT ON TABLES TO svc_notes_ro;"

# Audit : ajout seul. Ni UPDATE, ni DELETE, ni TRUNCATE (risque R23).
droits audit_db "GRANT USAGE ON SCHEMA public TO svc_audit;
ALTER DEFAULT PRIVILEGES FOR ROLE scolaris_migration IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO svc_audit;"

# Notifications : lecture, ajout et marquage « lue » ; jamais de suppression.
droits notifications_db "GRANT USAGE ON SCHEMA public TO svc_notifications;
ALTER DEFAULT PRIVILEGES FOR ROLE scolaris_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO svc_notifications;"
