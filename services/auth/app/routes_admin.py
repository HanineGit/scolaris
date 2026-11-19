"""F03 : gestion des comptes du personnel et des rôles (administrateur uniquement)."""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, Principal, exiger_roles

from .db import session as db_session
from .models import Utilisateur
from .schemas import CompteVue, CreationCompte, ModificationCompte
from .services import preparer_activation, revoquer, tracer

router = APIRouter(prefix="/api/v1/admin/comptes", tags=["comptes du personnel"])
admin = exiger_roles(ADMINISTRATEUR)


def _vue(u: Utilisateur) -> CompteVue:
    return CompteVue(
        id=u.id, identifiant=u.identifiant, email=u.email, nom=u.nom, prenom=u.prenom, role=u.role,
        statut=u.statut, derniere_connexion=u.derniere_connexion.isoformat() if u.derniere_connexion else None,
    )


def _compte_personnel(session: Session, compte_id: uuid.UUID) -> Utilisateur:
    u = session.get(Utilisateur, compte_id)
    if u is None or u.role == "ETUDIANT":
        raise ErreurMetier(404, "Compte introuvable.", "INTROUVABLE")
    return u


@router.get("", response_model=dict)
def lister(
    q: str | None = Query(default=None, max_length=60),
    role: str | None = Query(default=None, pattern="^(ENSEIGNANT|ADMINISTRATEUR)$"),
    page: int = Query(default=1, ge=1, le=10_000),
    taille: int = Query(default=20, ge=1, le=50),
    principal: Principal = Depends(admin), session: Session = Depends(db_session),
):
    requete = select(Utilisateur).where(Utilisateur.role != "ETUDIANT")
    if role:
        requete = requete.where(Utilisateur.role == role)
    if q:
        motif = f"%{q.lower()}%"  # valeur passée en paramètre lié, jamais concaténée au SQL
        requete = requete.where(or_(func.lower(Utilisateur.nom).like(motif), func.lower(Utilisateur.identifiant).like(motif)))
    total = session.scalar(select(func.count()).select_from(requete.subquery()))
    comptes = session.scalars(requete.order_by(Utilisateur.nom).offset((page - 1) * taille).limit(taille)).all()
    return {"total": total, "page": page, "elements": [_vue(u).model_dump(mode="json") for u in comptes]}


@router.post("", response_model=CompteVue, status_code=201)
def creer(donnees: CreationCompte, request: Request, principal: Principal = Depends(admin),
          session: Session = Depends(db_session)):
    u = Utilisateur(
        identifiant=donnees.email.split("@")[0], email=donnees.email, nom=donnees.nom.upper(),
        prenom=donnees.prenom, role=donnees.role, statut="EN_ATTENTE_ACTIVATION", cree_par=principal.id,
    )
    session.add(u)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Un compte utilise déjà cette adresse e-mail.", "DOUBLON")
    envoyer = preparer_activation(session, u)
    tracer(session, request, "COMPTE_CREE", "SUCCES", acteur=principal,
           ressource="utilisateur", ressource_id=u.id, details={"role_attribue": u.role})
    session.commit()
    envoyer(request.app.state.expediteur)
    return _vue(u)


@router.patch("/{compte_id}", response_model=CompteVue)
def modifier(compte_id: uuid.UUID, donnees: ModificationCompte, request: Request,
             principal: Principal = Depends(admin), session: Session = Depends(db_session)):
    u = _compte_personnel(session, compte_id)
    if u.id == principal.id:
        raise ErreurMetier(409, "Vous ne pouvez pas modifier votre propre compte.", "AUTO_MODIFICATION")
    retire_admin = u.role == "ADMINISTRATEUR" and (
        (donnees.role and donnees.role != "ADMINISTRATEUR") or donnees.statut == "DESACTIVE")
    if retire_admin:
        restants = session.scalar(select(func.count()).where(
            Utilisateur.role == "ADMINISTRATEUR", Utilisateur.statut == "ACTIF", Utilisateur.id != u.id))
        if restants == 0:
            raise ErreurMetier(409, "Il doit rester au moins un administrateur actif.", "DERNIER_ADMIN")
    diffuser = None
    if donnees.role and donnees.role != u.role:
        tracer(session, request, "ROLE_ATTRIBUE", "SUCCES", acteur=principal,
               ressource="utilisateur", ressource_id=u.id, details={"avant": u.role, "apres": donnees.role})
        u.role = donnees.role
        # Les jetons émis avec l'ancien rôle cessent immédiatement d'être acceptés (R06).
        diffuser = revoquer(session, request, u.id)
    if donnees.statut and donnees.statut != u.statut:
        if donnees.statut == "DESACTIVE":
            # La désactivation coupe immédiatement toutes les sessions ouvertes (R07).
            diffuser = revoquer(session, request, u.id)
            action = "COMPTE_DESACTIVE"
        else:
            action = "COMPTE_REACTIVE"
        u.statut = donnees.statut if (donnees.statut == "DESACTIVE" or u.hash_mot_de_passe) else u.statut
        tracer(session, request, action, "SUCCES", acteur=principal,
               ressource="utilisateur", ressource_id=u.id)
    session.commit()
    if diffuser:
        diffuser()
    return _vue(u)


@router.post("/{compte_id}/mfa/reinitialiser", status_code=204)
def reinitialiser_mfa(compte_id: uuid.UUID, request: Request, principal: Principal = Depends(admin),
                      session: Session = Depends(db_session)):
    """Perte du téléphone : le compte repasse en attente d'activation avec un nouveau lien."""
    u = _compte_personnel(session, compte_id)
    u.secret_mfa_chiffre = None
    u.statut = "EN_ATTENTE_ACTIVATION"
    diffuser = revoquer(session, request, u.id)
    envoyer = preparer_activation(session, u)
    tracer(session, request, "MFA_REINITIALISE", "SUCCES", acteur=principal,
           ressource="utilisateur", ressource_id=u.id)
    session.commit()
    diffuser()
    envoyer(request.app.state.expediteur)


@router.post("/{compte_id}/activation/renvoyer", status_code=204)
def renvoyer_activation(compte_id: uuid.UUID, request: Request, principal: Principal = Depends(admin),
                        session: Session = Depends(db_session)):
    """Renvoi du lien (relais SMTP indisponible, lien expiré : R31). Valable aussi pour un étudiant."""
    u = session.get(Utilisateur, compte_id)
    if u is None or u.statut != "EN_ATTENTE_ACTIVATION":
        raise ErreurMetier(409, "Ce compte n'est pas en attente d'activation.", "ETAT_INVALIDE")
    envoyer = preparer_activation(session, u)
    tracer(session, request, "ACTIVATION_RENVOYEE", "SUCCES", acteur=principal,
           ressource="utilisateur", ressource_id=u.id)
    session.commit()
    envoyer(request.app.state.expediteur)
