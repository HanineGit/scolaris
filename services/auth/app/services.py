"""Logique commune : audit, création de comptes et liens d'activation."""
import logging
from datetime import timedelta

from sqlalchemy import update

from scolaris_common import audit, revocation
from scolaris_common.config import parametre

from .mail import message_activation
from .models import (
    EvenementSortant, HistoriqueConnexion, JetonActivation, JetonRafraichissement, Revocation, SessionOuverte,
    Utilisateur,
)
from .tokens import empreinte, maintenant, nouveau_jeton_activation

SERVICE = "auth"
DUREE_ACTIVATION = timedelta(hours=24)


tracer = audit.Traceur(SERVICE, EvenementSortant)
log = logging.getLogger("auth.revocation")


def revoquer(session, request, utilisateur_id):
    """Révoque toutes les sessions d'un compte, y compris les jetons d'accès déjà émis.

    Retourne la fonction de diffusion à appeler après le commit : le registre
    local est mis à jour et la révocation est publiée aux autres services.
    """
    session.execute(update(JetonRafraichissement).where(JetonRafraichissement.utilisateur_id == utilisateur_id)
                    .values(revoque=True))
    session.execute(update(SessionOuverte).where(SessionOuverte.utilisateur_id == utilisateur_id).values(fermee=True))
    instant = revocation.maintenant_ms()
    session.add(Revocation(utilisateur_id=utilisateur_id, instant_ms=instant))

    def diffuser():
        etat = request.app.state
        etat.revocations.ajouter(str(utilisateur_id), instant)
        publier = getattr(etat, "publier_revocation", None)
        if publier:
            try:
                publier(str(utilisateur_id), instant)
            except Exception:
                # Les autres services se resynchronisent toutes les 30 secondes.
                log.warning("Diffusion de la révocation impossible ; resynchronisation périodique.")

    return diffuser


def preparer_activation(session, u: Utilisateur):
    """Invalide les liens précédents et crée un nouveau lien d'activation.

    Retourne une fonction d'envoi à appeler APRÈS le commit, pour ne jamais
    envoyer un lien qui n'aurait pas été enregistré. Le jeton est placé après
    « # » : il n'est ni transmis au serveur web ni conservé dans ses journaux.
    """
    for ancien in session.query(JetonActivation).filter_by(utilisateur_id=u.id, utilise=False):
        ancien.utilise = True
    valeur = nouveau_jeton_activation()
    session.add(JetonActivation(
        utilisateur_id=u.id, empreinte=empreinte(valeur), expire_le=maintenant() + DUREE_ACTIVATION,
    ))
    base = parametre("URL_ACTIVATION", "https://localhost/activation")
    texte = message_activation(f"{base}#jeton={valeur}", u.role)
    destinataire = u.email

    def envoyer(expediteur):
        expediteur.envoyer(destinataire, "Activation de votre compte Scolaris", texte)

    return envoyer


# --- F27 Espace sécurité : appareils, historique des connexions, alertes ---

NAVIGATEURS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
SYSTEMES = (("Android", "Android"), ("iPhone", "iOS"), ("iPad", "iPadOS"), ("Windows", "Windows"),
            ("Mac OS X", "macOS"), ("Linux", "Linux"))


def decrire_appareil(user_agent: str | None) -> str:
    """Résumé lisible et non identifiant de l'appareil ; la chaîne brute n'est jamais stockée."""
    ua = user_agent or ""
    systeme = next((nom for motif, nom in SYSTEMES if motif in ua), "système inconnu")
    if "okhttp" in ua or "Expo" in ua or "Scolaris" in ua or "CFNetwork" in ua:
        return f"Application Scolaris sous {systeme}"
    navigateur = next((nom for motif, nom in NAVIGATEURS if motif in ua), "Navigateur")
    return f"{navigateur} sous {systeme}"[:80]


def journaliser_connexion(session, request, u: Utilisateur, resultat: str) -> str:
    appareil = decrire_appareil(request.headers.get("user-agent"))
    session.add(HistoriqueConnexion(utilisateur_id=u.id, resultat=resultat, appareil=appareil,
                                    adresse_ip=audit.adresse_ip(request)))
    return appareil


def notifier(session, **kw) -> None:
    audit.notifier(session, EvenementSortant, **kw)
