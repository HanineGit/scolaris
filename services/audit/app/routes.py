"""F13 : consultation du journal d'audit, réservée à l'administrateur, en lecture seule."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, Principal, exiger_roles

from . import chaine
from .models import EvenementAudit, VerificationIntegrite

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
admin = exiger_roles(ADMINISTRATEUR)


def db(request: Request):
    yield from request.app.state.bdd.session()


def _resume(e: EvenementAudit) -> dict:
    return {"id": str(e.id), "numero": e.numero, "horodatage": e.horodatage.isoformat(),
            "acteur": e.acteur_identifiant, "role": e.role, "action": e.action, "ressource": e.ressource,
            "ressource_id": e.ressource_id, "resultat": e.resultat, "adresse_ip": e.adresse_ip}


@router.get("/evenements")
def lister(
    du: date | None = None, au: date | None = None,
    action: str | None = Query(default=None, pattern=r"^[A-Z_]{3,40}$"),
    resultat: str | None = Query(default=None, pattern=r"^(SUCCES|ECHEC|REFUSE|ALERTE)$"),
    acteur: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1, le=100_000), taille: int = Query(default=20, ge=1, le=50),
    principal: Principal = Depends(admin), session: Session = Depends(db),
):
    requete = select(EvenementAudit)
    if du:
        requete = requete.where(EvenementAudit.horodatage >= datetime.combine(du, time.min, timezone.utc))
    if au:
        requete = requete.where(EvenementAudit.horodatage < datetime.combine(au + timedelta(days=1), time.min, timezone.utc))
    if action:
        requete = requete.where(EvenementAudit.action == action)
    if resultat:
        requete = requete.where(EvenementAudit.resultat == resultat)
    if acteur:
        requete = requete.where(func.lower(EvenementAudit.acteur_identifiant).like(f"%{acteur.lower()}%"))
    total = session.scalar(select(func.count()).select_from(requete.subquery()))
    evenements = session.scalars(requete.order_by(EvenementAudit.numero.desc())
                                 .offset((page - 1) * taille).limit(taille)).all()
    return {"total": total, "page": page, "elements": [_resume(e) for e in evenements]}


@router.get("/actions")
def actions(principal: Principal = Depends(admin), session: Session = Depends(db)):
    return sorted(session.scalars(select(EvenementAudit.action).distinct()).all())


@router.get("/evenements/{evenement_id}")
def detail(evenement_id: uuid.UUID, principal: Principal = Depends(admin), session: Session = Depends(db)):
    e = session.scalar(select(EvenementAudit).where(EvenementAudit.id == evenement_id))
    if e is None:
        raise ErreurMetier(404, "Événement introuvable.", "INTROUVABLE")
    return {**_resume(e), "service": e.service, "id_correlation": e.id_correlation, "details": e.details,
            "empreinte_precedente": e.empreinte_precedente, "empreinte": e.empreinte}


def _vue_verification(v: VerificationIntegrite | None) -> dict:
    if v is None:
        return {"integre": None, "effectuee_le": None, "nombre": 0, "premier_defaut": None}
    return {"integre": v.integre, "effectuee_le": v.effectuee_le.isoformat(), "nombre": v.nombre,
            "premier_defaut": v.premier_defaut}


@router.get("/integrite")
def integrite(principal: Principal = Depends(admin), session: Session = Depends(db)):
    derniere = session.scalar(select(VerificationIntegrite).order_by(VerificationIntegrite.effectuee_le.desc()).limit(1))
    return _vue_verification(derniere)


@router.post("/integrite/verification")
def lancer_verification(request: Request, principal: Principal = Depends(admin)):
    return _vue_verification(chaine.verifier(request.app.state.bdd.fabrique))
