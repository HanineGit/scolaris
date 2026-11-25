"""Procédure de secours : un administrateur a perdu son mot de passe et son second facteur.

    docker compose exec auth python -m app.recuperer <adresse e-mail du compte>

Réservée à l'exploitant du serveur (accès au conteneur, donc à l'hôte). Le compte repasse
en attente d'activation : mot de passe et secret TOTP effacés, sessions révoquées, nouveau
lien d'activation envoyé à l'adresse du compte. L'opération est tracée en alerte dans le
journal d'audit. Le lien n'est jamais affiché : il part uniquement par e-mail.
"""
import sys

from sqlalchemy import select, update

from scolaris_common import logs, revocation
from scolaris_common.config import lire_secret

from . import db
from .mail import ExpediteurSmtp
from .models import JetonRafraichissement, Revocation, SessionOuverte, Utilisateur
from .services import preparer_activation, tracer


def main(email: str, initialiser: bool = True) -> int:
    log = logs.configurer("auth.recuperation")
    if initialiser:  # les tests fournissent leur propre base
        db.initialiser(lire_secret("auth_db_url"))
    with db.fabrique()() as s:
        u = s.scalar(select(Utilisateur).where(Utilisateur.email == email.lower()))
        if u is None or u.role == "ETUDIANT":
            log.error("Aucun compte du personnel ne correspond à cette adresse.")
            return 1
        u.hash_mot_de_passe = None
        u.secret_mfa_chiffre = u.secret_mfa_en_attente = None
        u.statut, u.tentatives_echouees, u.verrouille_jusqua = "EN_ATTENTE_ACTIVATION", 0, None
        # Toutes les sessions ouvertes sont fermées, jetons d'accès déjà émis compris.
        s.execute(update(JetonRafraichissement).where(JetonRafraichissement.utilisateur_id == u.id).values(revoque=True))
        s.execute(update(SessionOuverte).where(SessionOuverte.utilisateur_id == u.id).values(fermee=True))
        instant = revocation.maintenant_ms()
        s.add(Revocation(utilisateur_id=u.id, instant_ms=instant))
        envoyer = preparer_activation(s, u)
        tracer(s, None, "COMPTE_RECUPERE", "ALERTE", ressource="utilisateur", ressource_id=u.id,
               details={"origine": "procedure_de_secours_exploitant"})
        s.commit()
        envoyer(ExpediteurSmtp())
        if initialiser:
            try:  # effet immédiat sur tous les services ; à défaut, resynchronisation sous 30 s
                revocation.publier(lire_secret("rabbitmq_url"), str(u.id), instant)
            except Exception:
                log.warning("Bus indisponible : la révocation sera appliquée à la prochaine resynchronisation.")
    log.info("Compte réinitialisé ; nouveau lien d'activation envoyé à l'adresse du compte.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
