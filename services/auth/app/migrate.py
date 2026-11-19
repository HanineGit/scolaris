"""Création du schéma et du premier administrateur.

Exécuté au déploiement avec le compte « migration » (droits DDL), jamais par
le service en fonctionnement, qui n'a que SELECT, INSERT et UPDATE.
"""
import logging

from sqlalchemy import select

from scolaris_common import logs
from scolaris_common.config import SecretManquant, lire_secret, parametre

from . import db
from .mail import ExpediteurSmtp
from .models import Base, Utilisateur
from .services import preparer_activation, tracer


def main():
    log = logs.configurer("auth.migration")
    moteur = db.initialiser(lire_secret("auth_db_url_migration"))
    Base.metadata.create_all(moteur)
    log.info("Schéma auth_db à jour.")

    email = parametre("ADMIN_INITIAL_EMAIL", "")
    if not email:
        return
    with db.fabrique()() as s:
        if s.scalar(select(Utilisateur).where(Utilisateur.role == "ADMINISTRATEUR")):
            return
        u = Utilisateur(identifiant=email.split("@")[0], email=email.lower(), nom="ADMINISTRATEUR",
                        prenom="Initial", role="ADMINISTRATEUR", statut="EN_ATTENTE_ACTIVATION")
        s.add(u)
        s.flush()
        envoyer = preparer_activation(s, u)
        tracer(s, None, "COMPTE_CREE", "SUCCES", ressource="utilisateur", ressource_id=u.id,
               details={"role_attribue": "ADMINISTRATEUR", "origine": "initialisation"})
        s.commit()
        envoyer(ExpediteurSmtp())
        # Le lien n'est jamais écrit dans les journaux : il est envoyé par e-mail.
        log.info("Premier administrateur créé ; lien d'activation envoyé par e-mail.")


if __name__ == "__main__":
    main()
