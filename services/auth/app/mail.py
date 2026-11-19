"""Envoi des e-mails d'activation via le relais SMTP (prestataire, risque transféré R31)."""
import logging
import smtplib
from email.message import EmailMessage

from scolaris_common.config import lire_secret, parametre

log = logging.getLogger("auth.mail")


class ExpediteurSmtp:
    def envoyer(self, destinataire: str, sujet: str, texte: str) -> None:
        msg = EmailMessage()
        msg["From"] = parametre("SMTP_EXPEDITEUR", "Scolaris <no-reply@scolaris.local>")
        msg["To"] = destinataire
        msg["Subject"] = sujet
        msg.set_content(texte)
        hote = parametre("SMTP_HOTE", "mailpit")
        port = int(parametre("SMTP_PORT", "1025"))
        with smtplib.SMTP(hote, port, timeout=10) as smtp:
            if parametre("SMTP_TLS", "0") == "1":
                smtp.starttls()
                smtp.login(parametre("SMTP_UTILISATEUR"), lire_secret("smtp_password"))
            smtp.send_message(msg)


class ExpediteurMemoire:
    """Utilisé dans les tests."""

    def __init__(self):
        self.envoyes: list[dict] = []

    def envoyer(self, destinataire: str, sujet: str, texte: str) -> None:
        self.envoyes.append({"a": destinataire, "sujet": sujet, "texte": texte})


def message_activation(lien: str, role: str) -> str:
    complement = (
        "\nVous configurerez ensuite le second facteur avec une application d'authentification "
        "(Google Authenticator, Microsoft Authenticator, FreeOTP…).\n"
        if role != "ETUDIANT" else ""
    )
    return (
        "Bonjour,\n\n"
        "Un compte Scolaris a été créé pour vous. Pour l'activer et choisir votre mot de passe, "
        f"ouvrez le lien suivant :\n\n{lien}\n\n"
        "Ce lien est personnel, valable 24 heures et utilisable une seule fois." + complement +
        "\nSi vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"
    )
