"""Routes publiques d'authentification : F01 (connexion, session) et F02 (activation)."""
import uuid
from datetime import timedelta

import pyotp
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from scolaris_common import audit
from scolaris_common.errors import ErreurMetier
from scolaris_common.security import Principal, decoder_jeton, principal_courant

from . import crypto, passwords, tokens
from .db import session as db_session
from .models import HistoriqueConnexion, JetonActivation, JetonRafraichissement, SessionOuverte, Utilisateur
from .schemas import (
    Activation, Connexion, EtapeMfa, Jetons, Rafraichissement, UtilisateurPublic,
    VerifActivation, VerificationMfa,
)
from .services import journaliser_connexion, notifier, revoquer, tracer

router = APIRouter(prefix="/api/v1/auth", tags=["authentification"])

PERSONNEL = {"ENSEIGNANT", "ADMINISTRATEUR"}
MAX_ECHECS = 5
DUREE_VERROU = timedelta(minutes=15)
ECHEC = ErreurMetier(401, "Identifiants invalides.", "IDENTIFIANTS_INVALIDES")


def _deverrouiller_si_expire(u: Utilisateur) -> None:
    if u.statut == "VERROUILLE" and u.verrouille_jusqua and u.verrouille_jusqua <= tokens.maintenant():
        u.statut, u.tentatives_echouees, u.verrouille_jusqua = "ACTIF", 0, None


def _echec(session: Session, request: Request, u: Utilisateur | None, motif: str) -> None:
    """Compte l'échec, verrouille au 5e et journalise. Le client reçoit toujours le même message."""
    if u is not None:
        u.tentatives_echouees += 1
        journaliser_connexion(session, request, u, "ECHEC")
        if u.tentatives_echouees >= MAX_ECHECS and u.statut == "ACTIF":
            u.statut = "VERROUILLE"
            u.verrouille_jusqua = tokens.maintenant() + DUREE_VERROU
            journaliser_connexion(session, request, u, "VERROUILLAGE")
            tracer(session, request, "COMPTE_VERROUILLE", "ALERTE", acteur=u,
                   ressource="utilisateur", ressource_id=u.id)
            notifier(session, categorie="SECURITE", titre="Compte verrouillé",
                     message="Après 5 tentatives infructueuses, votre compte est verrouillé 15 minutes. "
                             "Si ce n'était pas vous, changez votre mot de passe.", utilisateurs=[u.id])
    tracer(session, request, "AUTH_ECHEC", "ECHEC", acteur=u,
           ressource="session", details={"motif": motif})
    session.commit()
    raise ECHEC


def _ouvrir_session(session: Session, request: Request, u: Utilisateur) -> Jetons:
    u.tentatives_echouees = 0
    u.derniere_connexion = tokens.maintenant()
    famille = uuid.uuid4()
    rafraichissement = tokens.nouveau_rafraichissement(session, u, famille=famille)
    deja_vus = set(session.scalars(select(HistoriqueConnexion.appareil).where(
        HistoriqueConnexion.utilisateur_id == u.id, HistoriqueConnexion.resultat == "SUCCES",
        HistoriqueConnexion.horodatage >= tokens.maintenant() - timedelta(days=90))))
    appareil = journaliser_connexion(session, request, u, "SUCCES")
    session.add(SessionOuverte(famille=famille, utilisateur_id=u.id, appareil=appareil,
                               adresse_ip=audit.adresse_ip(request)))
    if deja_vus and appareil not in deja_vus:
        # Alerte : connexion depuis un appareil inhabituel pour ce compte.
        notifier(session, categorie="SECURITE", titre="Nouvelle connexion",
                 message=f"Connexion depuis un nouvel appareil ({appareil}). Si ce n'était pas vous, "
                         "fermez cette session dans l'espace sécurité et changez votre mot de passe.",
                 lien="/securite", utilisateurs=[u.id])
    tracer(session, request, "AUTH_SUCCES", "SUCCES", acteur=u, ressource="session", details={"appareil": appareil})
    session.commit()
    return Jetons(
        jeton_acces=tokens.jeton_acces(u, famille),
        jeton_rafraichissement=rafraichissement,
        utilisateur=UtilisateurPublic(id=u.id, identifiant=u.identifiant, role=u.role, nom=u.nom, prenom=u.prenom),
    )


@router.post("/connexion", response_model=Jetons | EtapeMfa)
def connexion(donnees: Connexion, request: Request, session: Session = Depends(db_session)):
    u = session.scalar(select(Utilisateur).where(
        (func.lower(Utilisateur.identifiant) == donnees.identifiant.lower())
        | (Utilisateur.email == donnees.identifiant.lower())
    ))
    # La vérification Argon2 a lieu même si le compte n'existe pas (temps constant, R03).
    valide = passwords.verifier(u.hash_mot_de_passe if u else None, donnees.mot_de_passe)
    if u is None:
        _echec(session, request, None, "compte_inconnu")
    _deverrouiller_si_expire(u)
    if u.statut != "ACTIF":
        _echec(session, request, u, f"statut_{u.statut.lower()}")
    if not valide:
        _echec(session, request, u, "mot_de_passe")
    if u.role in PERSONNEL:
        session.commit()
        return EtapeMfa(jeton_mfa=tokens.jeton_mfa(u))
    return _ouvrir_session(session, request, u)


@router.post("/mfa/verifier", response_model=Jetons)
def verifier_mfa(donnees: VerificationMfa, request: Request, session: Session = Depends(db_session)):
    charge = decoder_jeton(donnees.jeton_mfa, type_attendu="mfa")
    u = session.get(Utilisateur, uuid.UUID(charge["sub"]))
    if u is None or u.role not in PERSONNEL or u.secret_mfa_chiffre is None:
        raise ECHEC
    _deverrouiller_si_expire(u)
    if u.statut != "ACTIF":
        _echec(session, request, u, f"statut_{u.statut.lower()}")
    totp = pyotp.TOTP(crypto.dechiffrer(u.secret_mfa_chiffre, u.id.bytes))
    pas = None
    courant = int(tokens.maintenant().timestamp()) // totp.interval
    for decalage in (-1, 0, 1):  # tolérance de ±30 s pour le décalage d'horloge
        if totp.verify(donnees.code, for_time=(courant + decalage) * totp.interval, valid_window=0):
            pas = courant + decalage
            break
    # Un code déjà utilisé est refusé (anti-rejeu).
    if pas is None or (u.mfa_dernier_pas is not None and pas <= u.mfa_dernier_pas):
        _echec(session, request, u, "code_totp")
    u.mfa_dernier_pas = pas
    return _ouvrir_session(session, request, u)


@router.post("/rafraichir", response_model=Jetons)
def rafraichir(donnees: Rafraichissement, request: Request, session: Session = Depends(db_session)):
    jeton = session.scalar(select(JetonRafraichissement).where(
        JetonRafraichissement.empreinte == tokens.empreinte(donnees.jeton_rafraichissement)))
    erreur = ErreurMetier(401, "Session invalide ou expirée.", "SESSION_INVALIDE")
    if jeton is None or jeton.revoque:
        # Jeton d'une session déjà fermée (déconnexion, appareil retiré) : simple refus, sans effet de bord.
        raise erreur
    if jeton.utilise:
        # Réutilisation d'un jeton déjà consommé : vol probable, toute la session est révoquée (R02).
        # Vol probable : les jetons d'accès déjà émis pour ce compte sont eux aussi révoqués.
        diffuser = revoquer(session, request, jeton.utilisateur_id)
        tracer(session, request, "SESSION_REVOQUEE", "ALERTE", acteur=jeton.utilisateur,
               ressource="session", details={"motif": "reutilisation_jeton"})
        session.commit()
        diffuser()
        raise erreur
    u = jeton.utilisateur
    if jeton.expire_le <= tokens.maintenant() or u.statut != "ACTIF":
        raise erreur
    jeton.utilise = True
    nouveau = tokens.nouveau_rafraichissement(session, u, famille=jeton.famille, debut=jeton.debut_famille)
    session.execute(update(SessionOuverte).where(SessionOuverte.famille == jeton.famille)
                    .values(derniere_activite=tokens.maintenant()))
    session.commit()
    return Jetons(
        jeton_acces=tokens.jeton_acces(u, jeton.famille), jeton_rafraichissement=nouveau,
        utilisateur=UtilisateurPublic(id=u.id, identifiant=u.identifiant, role=u.role, nom=u.nom, prenom=u.prenom),
    )


@router.post("/deconnexion", status_code=204)
def deconnexion(donnees: Rafraichissement, request: Request, principal: Principal = Depends(principal_courant),
                session: Session = Depends(db_session)):
    jeton = session.scalar(select(JetonRafraichissement).where(
        JetonRafraichissement.empreinte == tokens.empreinte(donnees.jeton_rafraichissement),
        JetonRafraichissement.utilisateur_id == principal.id))
    if jeton is not None:
        session.execute(update(JetonRafraichissement).where(JetonRafraichissement.famille == jeton.famille)
                        .values(revoque=True))
        session.execute(update(SessionOuverte).where(SessionOuverte.famille == jeton.famille).values(fermee=True))
    tracer(session, request, "DECONNEXION", "SUCCES", acteur=principal, ressource="session")
    session.commit()


def _jeton_activation_valide(session: Session, valeur: str) -> JetonActivation:
    j = session.scalar(select(JetonActivation).where(JetonActivation.empreinte == tokens.empreinte(valeur)))
    if j is None or j.utilise or j.expire_le <= tokens.maintenant() or j.utilisateur.statut != "EN_ATTENTE_ACTIVATION":
        raise ErreurMetier(400, "Ce lien d'activation est invalide ou a expiré.", "LIEN_INVALIDE")
    return j


@router.post("/activation/verifier")
def verifier_activation(donnees: VerifActivation, session: Session = Depends(db_session)):
    """Prépare l'activation : pour le personnel, génère le secret TOTP à enregistrer."""
    j = _jeton_activation_valide(session, donnees.jeton)
    u = j.utilisateur
    reponse = {"identifiant": u.identifiant, "role": u.role, "expire_le": j.expire_le.isoformat(), "mfa_requis": False}
    if u.role in PERSONNEL:
        secret = pyotp.random_base32()
        u.secret_mfa_en_attente = crypto.chiffrer(secret, u.id.bytes)
        session.commit()
        reponse.update(mfa_requis=True, mfa_uri=pyotp.TOTP(secret).provisioning_uri(u.email, issuer_name="Scolaris"))
    return reponse


@router.post("/activation", status_code=204)
def activer(donnees: Activation, request: Request, session: Session = Depends(db_session)):
    j = _jeton_activation_valide(session, donnees.jeton)
    u = j.utilisateur
    if donnees.mot_de_passe != donnees.confirmation:
        raise ErreurMetier(422, "Les deux mots de passe ne correspondent pas.", "CONFIRMATION")
    regles = passwords.regles_non_respectees(donnees.mot_de_passe, u.identifiant, u.email)
    if regles:
        raise ErreurMetier(422, "Le mot de passe doit contenir : " + ", ".join(regles) + ".", "POLITIQUE_MDP")
    if u.role in PERSONNEL:
        if u.secret_mfa_en_attente is None or donnees.code_totp is None:
            raise ErreurMetier(422, "Le code de l'application d'authentification est requis.", "MFA_REQUIS")
        secret = crypto.dechiffrer(u.secret_mfa_en_attente, u.id.bytes)
        if not pyotp.TOTP(secret).verify(donnees.code_totp, valid_window=1):
            raise ErreurMetier(422, "Code de vérification incorrect.", "MFA_INCORRECT")
        u.secret_mfa_chiffre, u.secret_mfa_en_attente = u.secret_mfa_en_attente, None
    u.hash_mot_de_passe = passwords.hacher(donnees.mot_de_passe)
    u.statut = "ACTIF"
    j.utilise = True
    tracer(session, request, "COMPTE_ACTIVE", "SUCCES", acteur=u, ressource="utilisateur", ressource_id=u.id)
    session.commit()
