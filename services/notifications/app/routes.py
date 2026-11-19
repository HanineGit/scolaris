"""F28 Centre de notifications : chaque utilisateur ne voit que les siennes."""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from scolaris_common.errors import ErreurMetier
from scolaris_common.security import Principal, principal_courant

from .models import Notification, maintenant

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def db(request: Request):
    yield from request.app.state.bdd.session()


def _miennes(principal: Principal):
    """Destinataire désigné par le compte (jeton « sub ») ou par la fiche étudiant (jeton « etu »)."""
    conditions = [Notification.utilisateur_id == principal.id]
    if principal.etudiant_id:
        conditions.append(Notification.etudiant_id == principal.etudiant_id)
    return or_(*conditions)


def _vue(n: Notification) -> dict:
    return {"id": str(n.id), "categorie": n.categorie, "titre": n.titre, "message": n.message, "lien": n.lien,
            "creee_le": n.creee_le.isoformat(), "lue": n.lue_le is not None}


@router.get("")
def lister(non_lues: bool = False, limite: int = Query(default=30, ge=1, le=100),
           principal: Principal = Depends(principal_courant), session: Session = Depends(db)):
    requete = select(Notification).where(_miennes(principal))
    if non_lues:
        requete = requete.where(Notification.lue_le.is_(None))
    lignes = session.scalars(requete.order_by(Notification.creee_le.desc()).limit(limite)).all()
    compte = session.scalar(select(func.count()).select_from(Notification)
                            .where(_miennes(principal), Notification.lue_le.is_(None)))
    return {"non_lues": compte, "elements": [_vue(n) for n in lignes]}


@router.post("/lecture", status_code=204)
def tout_marquer_lu(principal: Principal = Depends(principal_courant), session: Session = Depends(db)):
    session.execute(update(Notification).where(_miennes(principal), Notification.lue_le.is_(None))
                    .values(lue_le=maintenant()))
    session.commit()


@router.post("/{notification_id}/lecture", status_code=204)
def marquer_lue(notification_id: uuid.UUID, principal: Principal = Depends(principal_courant),
                session: Session = Depends(db)):
    # Même réponse qu'une notification inexistante : on ne révèle pas celles des autres.
    n = session.scalar(select(Notification).where(Notification.id == notification_id, _miennes(principal)))
    if n is None:
        raise ErreurMetier(404, "Notification introuvable.", "INTROUVABLE")
    if n.lue_le is None:
        n.lue_le = maintenant()
        session.commit()
