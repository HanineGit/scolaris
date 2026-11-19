"""Routes internes (non exposées par la passerelle), protégées par jeton de service."""
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scolaris_common.errors import ErreurMetier
from scolaris_common import revocation
from scolaris_common.security import exiger_service

from .db import session as db_session
from .models import Revocation, Utilisateur
from .schemas import CompteEtudiant, EmailInterne, EtatsInternes, StatutInterne
from .services import preparer_activation, revoquer, tracer

router = APIRouter(prefix="/internal/comptes", tags=["interne"], include_in_schema=False)


@router.post("/etudiants", status_code=201, dependencies=[Depends(exiger_service("service_token_etudiants"))])
def creer_compte_etudiant(donnees: CompteEtudiant, request: Request, session: Session = Depends(db_session)):
    """Appelé par le service Étudiants lors de l'ajout d'un étudiant (F04 → F02)."""
    u = Utilisateur(identifiant=donnees.matricule, email=donnees.email, role="ETUDIANT",
                    statut="EN_ATTENTE_ACTIVATION", etudiant_id=donnees.etudiant_id)
    session.add(u)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Un compte existe déjà pour cet étudiant ou cette adresse.", "DOUBLON")
    envoyer = preparer_activation(session, u)
    tracer(session, request, "COMPTE_CREE", "SUCCES", ressource="utilisateur", ressource_id=u.id,
           details={"role_attribue": "ETUDIANT", "origine": "service_etudiants"})
    session.commit()
    envoyer(request.app.state.expediteur)
    return {"utilisateur_id": str(u.id)}


@router.patch("/{utilisateur_id}/statut", status_code=204,
              dependencies=[Depends(exiger_service("service_token_etudiants"))])
def changer_statut(utilisateur_id: uuid.UUID, donnees: StatutInterne, request: Request,
                   session: Session = Depends(db_session)):
    """Archivage d'un étudiant (F06) : son compte est désactivé et ses sessions révoquées."""
    u = session.get(Utilisateur, utilisateur_id)
    if u is None or u.role != "ETUDIANT":
        raise ErreurMetier(404, "Compte introuvable.", "INTROUVABLE")
    diffuser = None
    if donnees.statut == "DESACTIVE":
        diffuser = revoquer(session, request, u.id)
        u.statut = "DESACTIVE"
    elif u.hash_mot_de_passe:
        u.statut = "ACTIF"
    tracer(session, request, "COMPTE_" + ("DESACTIVE" if donnees.statut == "DESACTIVE" else "REACTIVE"), "SUCCES",
           ressource="utilisateur", ressource_id=u.id, details={"origine": "service_etudiants"})
    session.commit()
    if diffuser:
        diffuser()


@router.get("/revocations", dependencies=[Depends(exiger_service(
    "service_token_etudiants", "service_token_notes", "service_token_audit", "service_token_notifications"))])
def revocations_recentes(session: Session = Depends(db_session)):
    """Resynchronisation des autres services : révocations des 16 dernières minutes."""
    limite = revocation.maintenant_ms() - revocation.DUREE_CONSERVATION_S * 1000
    lignes = session.scalars(select(Revocation).where(Revocation.instant_ms >= limite)).all()
    return [{"utilisateur_id": str(r.utilisateur_id), "instant_ms": r.instant_ms} for r in lignes]


@router.get("/{utilisateur_id}", dependencies=[Depends(exiger_service("service_token_notes", "service_token_etudiants"))])
def lire_compte(utilisateur_id: uuid.UUID, session: Session = Depends(db_session)):
    """Utilisé par le service Notes pour vérifier qu'un compte est bien un enseignant actif (F07)."""
    u = session.get(Utilisateur, utilisateur_id)
    if u is None:
        raise ErreurMetier(404, "Compte introuvable.", "INTROUVABLE")
    return {"id": str(u.id), "role": u.role, "statut": u.statut, "nom": u.nom, "prenom": u.prenom}


@router.get("", dependencies=[Depends(exiger_service("service_token_notes"))])
def lister_enseignants(session: Session = Depends(db_session)):
    """Liste des enseignants actifs, pour le choix d'une affectation (F07)."""
    ens = session.scalars(select(Utilisateur).where(Utilisateur.role == "ENSEIGNANT", Utilisateur.statut == "ACTIF")
                          .order_by(Utilisateur.nom)).all()
    return [{"id": str(u.id), "nom": u.nom, "prenom": u.prenom} for u in ens]


@router.patch("/{utilisateur_id}/email", status_code=204,
              dependencies=[Depends(exiger_service("service_token_etudiants"))])
def changer_email(utilisateur_id: uuid.UUID, donnees: EmailInterne, request: Request,
                  session: Session = Depends(db_session)):
    """Correction de l'adresse d'un étudiant (F06) : l'adresse de connexion suit la fiche."""
    u = session.get(Utilisateur, utilisateur_id)
    if u is None or u.role != "ETUDIANT":
        raise ErreurMetier(404, "Compte introuvable.", "INTROUVABLE")
    u.email = donnees.email
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Cette adresse e-mail est déjà utilisée.", "DOUBLON")
    tracer(session, request, "COMPTE_MODIFIE", "SUCCES", ressource="utilisateur", ressource_id=u.id,
           details={"champ": "email", "origine": "service_etudiants"})
    session.commit()


@router.post("/etats", dependencies=[Depends(exiger_service("service_token_etudiants"))])
def etats(donnees: EtatsInternes, session: Session = Depends(db_session)):
    """État des comptes d'une page d'étudiants (activé, en attente, verrouillé)."""
    comptes = session.scalars(select(Utilisateur).where(Utilisateur.id.in_(donnees.ids))).all()
    return {str(u.id): u.statut for u in comptes}
