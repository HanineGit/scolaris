"""Génère tous les secrets de l'environnement local dans ./secrets (jamais versionné).

Usage : python scripts/generer_secrets.py [--forcer | --completer]

--completer ajoute seulement les secrets manquants (nouveau service) sans toucher aux existants.

Chaque secret est un fichier distinct, monté par Docker en lecture seule
dans /run/secrets/<nom> du seul conteneur qui en a besoin.
"""
import base64
import datetime
import ipaddress
import json
import os
import secrets
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

RACINE = Path(__file__).resolve().parents[1]
DOSSIER = RACINE / "secrets"


COMPLETER = "--completer" in sys.argv


def ecrire(nom: str, contenu: str | bytes) -> None:
    chemin = DOSSIER / nom
    if COMPLETER and chemin.exists():
        return  # secret existant conservé : les bases et comptes déjà créés restent valides
    if isinstance(contenu, str):
        contenu = contenu.encode()
    chemin.write_bytes(contenu)
    try:
        os.chmod(chemin, 0o600)
    except OSError:
        pass


def mot_de_passe() -> str:
    return secrets.token_urlsafe(32)


def certificat_auto_signe():
    """Certificat TLS de développement pour la passerelle (remplacé par un vrai certificat en production)."""
    cle = ec.generate_private_key(ec.SECP256R1())
    nom = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
                     x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Scolaris (developpement)")])
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nom).issuer_name(nom).public_key(cle.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(maintenant - datetime.timedelta(minutes=5))
            .not_valid_after(maintenant + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                        x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(cle, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM),
            cle.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


def autorite_interne():
    """Autorité de certification interne : chiffre les flux vers PostgreSQL et RabbitMQ."""
    cle = ec.generate_private_key(ec.SECP256R1())
    nom = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Scolaris AC interne")])
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nom).issuer_name(nom).public_key(cle.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(maintenant - datetime.timedelta(minutes=5))
            .not_valid_after(maintenant + datetime.timedelta(days=730))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                         crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .sign(cle, hashes.SHA256()))
    return cle, cert


def certificat_serveur(ac_cle, ac_cert, nom_dns: str):
    cle = ec.generate_private_key(ec.SECP256R1())
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nom_dns)]))
            .issuer_name(ac_cert.subject).public_key(cle.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(maintenant - datetime.timedelta(minutes=5))
            .not_valid_after(maintenant + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(nom_dns)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ac_cle, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM),
            cle.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                              serialization.NoEncryption()))


def empreinte_spki(cle_publique) -> str:
    """Empreinte SHA-256 (base64) de la clé publique, utilisée pour l'épinglage mobile."""
    import hashlib
    der = cle_publique.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(hashlib.sha256(der).digest()).decode()


def main():
    if DOSSIER.exists() and any(DOSSIER.iterdir()) and "--forcer" not in sys.argv and not COMPLETER:
        print("Le dossier secrets/ existe déjà. Relancez avec --completer (secrets manquants seulement) "
              "ou --forcer (tout régénérer).")
        return
    DOSSIER.mkdir(exist_ok=True)

    # Signature des jetons : RSA 3072 bits.
    cle = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ecrire("jwt_private_key", cle.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                serialization.NoEncryption()))
    ecrire("jwt_public_key", cle.public_key().public_bytes(serialization.Encoding.PEM,
                                                           serialization.PublicFormat.SubjectPublicKeyInfo))
    ecrire("mfa_encryption_key", base64.b64encode(os.urandom(32)).decode())

    # Jetons de service : un par service appelant.
    ecrire("service_token_etudiants", mot_de_passe())
    ecrire("service_token_notes", mot_de_passe())
    ecrire("service_token_audit", mot_de_passe())
    ecrire("service_token_notifications", mot_de_passe())

    # PostgreSQL : un compte de migration (DDL) et un compte par service (droits minimaux).
    comptes = {"postgres_admin": "postgres", "migration": "scolaris_migration", "svc_auth": "svc_auth",
               "svc_etudiant": "svc_etudiant", "svc_notes_rw": "svc_notes_rw", "svc_notes_ro": "svc_notes_ro",
               "svc_audit": "svc_audit", "svc_notifications": "svc_notifications"}

    def existant_ou_nouveau(cle_: str) -> str:
        chemin = DOSSIER / f"pg_{cle_}_password"
        return chemin.read_text().strip() if COMPLETER and chemin.exists() else mot_de_passe()

    mdp = {cle_: existant_ou_nouveau(cle_) for cle_ in comptes}
    for cle_, valeur in mdp.items():
        ecrire(f"pg_{cle_}_password", valeur)
    hote = "postgres:5432"

    def url(compte: str, base: str) -> str:
        # verify-full : chiffrement obligatoire et vérification du certificat et du nom du serveur.
        return (f"postgresql+psycopg://{comptes[compte]}:{mdp[compte]}@{hote}/{base}"
                "?sslmode=verify-full&sslrootcert=/run/secrets/ca_cert")

    ecrire("auth_db_url", url("svc_auth", "auth_db"))
    ecrire("etudiant_db_url", url("svc_etudiant", "etudiant_db"))
    ecrire("notes_db_url", url("svc_notes_rw", "notes_db"))
    ecrire("notes_db_url_ro", url("svc_notes_ro", "notes_db"))
    ecrire("audit_db_url", url("svc_audit", "audit_db"))
    ecrire("notifications_db_url", url("svc_notifications", "notifications_db"))
    for base in ("auth_db", "etudiant_db", "notes_db", "audit_db", "notifications_db"):
        ecrire(f"{base}_url_migration", url("migration", base))

    # RabbitMQ.
    mdp_rabbit = mot_de_passe()
    ecrire("rabbitmq_password", mdp_rabbit)
    ecrire("rabbitmq_url", f"amqps://scolaris:{mdp_rabbit}@rabbitmq:5671/%2F")

    # Chiffrement interne (PostgreSQL, RabbitMQ) par une autorité de certification propre au projet.
    ac_cle, ac_cert = autorite_interne()
    ecrire("ca_cert", ac_cert.public_bytes(serialization.Encoding.PEM))
    for nom in ("postgres", "rabbitmq"):
        c, k = certificat_serveur(ac_cle, ac_cert, nom)
        ecrire(f"{nom}_tls_cert", c)
        ecrire(f"{nom}_tls_key", k)

    # Sauvegardes chiffrées (AES-256-GCM).
    ecrire("backup_key", base64.b64encode(os.urandom(32)).decode())

    # Relais SMTP (prestataire en production ; Mailpit sans authentification en développement).
    ecrire("smtp_password", mot_de_passe())

    cert, cle_tls = certificat_auto_signe()
    ecrire("tls_cert", cert)
    ecrire("tls_key", cle_tls)
    # Clé de secours de la passerelle, conservée hors ligne : son empreinte est épinglée
    # dans l'application mobile pour permettre un renouvellement sans mise à jour.
    secours = ec.generate_private_key(ec.SECP256R1())
    ecrire("tls_backup_key", secours.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
    actuelle = x509.load_pem_x509_certificate(cert).public_key()
    empreintes = [empreinte_spki(actuelle), empreinte_spki(secours.public_key())]
    fichier_empreintes = RACINE / "mobile" / "empreintes_tls.json"
    if not (COMPLETER and fichier_empreintes.exists()):  # sinon les empreintes ne correspondraient plus aux clés
        fichier_empreintes.write_text(json.dumps(empreintes, indent=2), encoding="utf-8")

    print(f"Secrets générés dans {DOSSIER} ({len(list(DOSSIER.iterdir()))} fichiers). Ne jamais les versionner.")


if __name__ == "__main__":
    main()
