"""F27 Espace sécurité (tous les profils) et indicateurs de sécurité de l'administrateur."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, Principal, decoder_jeton, exiger_roles, principal_courant

from . import passwords, tokens
from .db import session as db_session
from .models import HistoriqueConnexion, JetonRafraichissement, SessionOuverte, Utilisateur
from .schemas import Strict
from .services import notifier, tracer

router = APIRouter(prefix="/api/v1/moi", tags=["espace sécurité"])
admin_router = APIRouter(prefix="/api/v1/admin/securite", tags=["administration"])
admin = exiger_roles(ADMINISTRATEUR)
MAX_ECHECS = 5


class ChangementMotDePasse(Strict):
    actuel: str = Field(min_length=1, max_length=128)
    nouveau: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=128)


def _famille_courante(request: Request) -> str | None:
    entete = request.headers.get("authorization", "")
    try:
        return decoder_jeton(entete.removeprefix("Bearer ").strip(), type_attendu="access").get("fam")
    except Exception:  # le jeton a déjà été validé par principal_courant
        return None


def _fermer(session: Session, famille: uuid.UUID) -> None:
    session.execute(update(JetonRafraichissement).where(JetonRafraichissement.famille == famille).values(revoque=True))
    session.execute(update(SessionOuverte).where(SessionOuverte.famille == famille).values(fermee=True))


def _sessions_actives(session: Session, utilisateur_id: uuid.UUID) -> list[SessionOuverte]:
    """Une session est active tant qu'un jeton de rafraîchissement non utilisé et non expiré existe."""
    vivantes = select(JetonRafraichissement.famille).where(
        JetonRafraichissement.utilisateur_id == utilisateur_id, JetonRafraichissement.revoque.is_(False),
        JetonRafraichissement.utilise.is_(False), JetonRafraichissement.expire_le > tokens.maintenant())
    return session.scalars(select(SessionOuverte).where(
        SessionOuverte.utilisateur_id == utilisateur_id, SessionOuverte.fermee.is_(False),
        SessionOuverte.famille.in_(vivantes)).order_by(SessionOuverte.derniere_activite.desc())).all()


@router.get("/securite")
def securite(request: Request, principal: Principal = Depends(principal_courant), session: Session = Depends(db_session)):
    u = session.get(Utilisateur, principal.id)
    courante = _famille_courante(request)
    connexions = session.scalars(select(HistoriqueConnexion).where(HistoriqueConnexion.utilisateur_id == principal.id)
                                 .order_by(HistoriqueConnexion.horodatage.desc()).limit(20)).all()
    return {
        "identifiant": u.identifiant, "email": u.email, "role": u.role,
        "double_facteur": u.secret_mfa_chiffre is not None,
        "derniere_connexion": u.derniere_connexion.isoformat() if u.derniere_connexion else None,
        "sessions": [{"id": str(s.famille), "appareil": s.appareil, "adresse_ip": s.adresse_ip,
                      "ouverte_le": s.ouverte_le.isoformat(), "derniere_activite": s.derniere_activite.isoformat(),
                      "courante": str(s.famille) == courante} for s in _sessions_actives(session, principal.id)],
        "connexions": [{"horodatage": c.horodatage.isoformat(), "resultat": c.resultat, "appareil": c.appareil,
                        "adresse_ip": c.adresse_ip} for c in connexions],
    }


@router.delete("/sessions/{famille}", status_code=204)
def fermer_session(famille: uuid.UUID, request: Request, principal: Principal = Depends(principal_courant),
                   session: Session = Depends(db_session)):
    s = session.get(SessionOuverte, famille)
    # Même réponse qu'une session inexistante : on ne révèle pas les sessions des autres comptes.
    if s is None or s.utilisateur_id != principal.id:
        raise ErreurMetier(404, "Session introuvable.", "INTROUVABLE")
    _fermer(session, famille)
    tracer(session, request, "SESSION_FERMEE", "SUCCES", acteur=principal, ressource="session",
           details={"appareil": s.appareil})
    session.commit()


@router.post("/sessions/fermeture-des-autres")
def fermer_les_autres(request: Request, principal: Principal = Depends(principal_courant),
                      session: Session = Depends(db_session)):
    courante = _famille_courante(request)
    fermees = 0
    for s in _sessions_actives(session, principal.id):
        if str(s.famille) != courante:
            _fermer(session, s.famille)
            fermees += 1
    tracer(session, request, "SESSIONS_FERMEES", "SUCCES", acteur=principal, ressource="session",
           details={"nombre": fermees})
    session.commit()
    return {"fermees": fermees}


@router.put("/mot-de-passe", status_code=204)
def changer_mot_de_passe(donnees: ChangementMotDePasse, request: Request,
                         principal: Principal = Depends(principal_courant), session: Session = Depends(db_session)):
    u = session.get(Utilisateur, principal.id)
    if not passwords.verifier(u.hash_mot_de_passe, donnees.actuel):
        # Un jeton volé ne suffit pas à changer le mot de passe : les erreurs comptent comme des échecs.
        u.tentatives_echouees += 1
        tracer(session, request, "MOT_DE_PASSE_ECHEC", "ECHEC", acteur=principal, ressource="utilisateur",
               ressource_id=u.id)
        if u.tentatives_echouees >= MAX_ECHECS:
            u.statut, u.verrouille_jusqua = "VERROUILLE", tokens.maintenant() + timedelta(minutes=15)
            tracer(session, request, "COMPTE_VERROUILLE", "ALERTE", acteur=principal, ressource="utilisateur",
                   ressource_id=u.id)
        session.commit()
        raise ErreurMetier(422, "Le mot de passe actuel est incorrect.", "MDP_ACTUEL")
    if donnees.nouveau != donnees.confirmation:
        raise ErreurMetier(422, "Les deux mots de passe ne correspondent pas.", "CONFIRMATION")
    if donnees.nouveau == donnees.actuel:
        raise ErreurMetier(422, "Le nouveau mot de passe doit être différent de l'actuel.", "IDENTIQUE")
    regles = passwords.regles_non_respectees(donnees.nouveau, u.identifiant, u.email)
    if regles:
        raise ErreurMetier(422, "Le mot de passe doit contenir : " + ", ".join(regles) + ".", "POLITIQUE_MDP")
    u.hash_mot_de_passe = passwords.hacher(donnees.nouveau)
    u.tentatives_echouees = 0
    courante = _famille_courante(request)
    for s in _sessions_actives(session, principal.id):
        if str(s.famille) != courante:
            _fermer(session, s.famille)  # les autres appareils doivent se reconnecter
    tracer(session, request, "MOT_DE_PASSE_MODIFIE", "SUCCES", acteur=principal, ressource="utilisateur", ressource_id=u.id)
    notifier(session, categorie="SECURITE", titre="Mot de passe modifié",
             message="Le mot de passe de votre compte vient d'être modifié. Vos autres sessions ont été fermées.",
             utilisateurs=[u.id])
    session.commit()


@admin_router.get("")
def indicateurs(principal: Principal = Depends(admin), session: Session = Depends(db_session)):
    depuis = tokens.maintenant() - timedelta(hours=24)
    par_resultat = dict(session.execute(select(HistoriqueConnexion.resultat, func.count())
                                        .where(HistoriqueConnexion.horodatage >= depuis)
                                        .group_by(HistoriqueConnexion.resultat)).all())
    par_statut = dict(session.execute(select(Utilisateur.statut, func.count()).group_by(Utilisateur.statut)).all())
    par_role = dict(session.execute(select(Utilisateur.role, func.count()).where(Utilisateur.statut == "ACTIF")
                                    .group_by(Utilisateur.role)).all())
    return {
        "connexions_24h": par_resultat.get("SUCCES", 0), "echecs_24h": par_resultat.get("ECHEC", 0),
        "verrouillages_24h": par_resultat.get("VERROUILLAGE", 0),
        "comptes_verrouilles": par_statut.get("VERROUILLE", 0),
        "comptes_en_attente": par_statut.get("EN_ATTENTE_ACTIVATION", 0),
        "comptes_actifs_par_role": par_role,
    }
