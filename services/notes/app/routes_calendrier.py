"""F17 Semestres et fenêtres de saisie ; F18 Publication et verrouillage des notes."""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scolaris_common.calendrier import annee_academique
from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, ENSEIGNANT, Principal, exiger_roles

from .models import Matiere, Note, Semestre, maintenant
from .schemas import CreationSemestre, Depublication, FenetreSaisie
from .services import classe, db, notifier, tracer, vue_semestre

router = APIRouter(prefix="/api/v1", tags=["calendrier"])
admin = exiger_roles(ADMINISTRATEUR)
personnel = exiger_roles(ENSEIGNANT, ADMINISTRATEUR)


def _semestre(session: Session, semestre_id: uuid.UUID) -> Semestre:
    s = session.get(Semestre, semestre_id)
    if s is None:
        raise ErreurMetier(404, "Semestre introuvable.", "INTROUVABLE")
    return s


@router.get("/semestres")
def lister(annee: str | None = Query(default=None, pattern=r"^\d{4}-\d{4}$"),
           principal: Principal = Depends(personnel), session: Session = Depends(db)):
    annee = annee or annee_academique()
    semestres = session.scalars(select(Semestre).where(Semestre.annee_academique == annee).order_by(Semestre.numero))
    return {"annee_academique": annee, "elements": [vue_semestre(s) for s in semestres]}


@router.post("/semestres", status_code=201)
def creer(donnees: CreationSemestre, request: Request, principal: Principal = Depends(admin),
          session: Session = Depends(db)):
    s = Semestre(**donnees.model_dump())
    session.add(s)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Ce semestre existe déjà pour cette année.", "DOUBLON")
    tracer(session, request, "SEMESTRE_CREE", "SUCCES", acteur=principal, ressource="semestre", ressource_id=s.id,
           details={"annee": s.annee_academique, "numero": s.numero})
    session.commit()
    return vue_semestre(s)


@router.put("/semestres/{semestre_id}/fenetre")
def ouvrir_fenetre(semestre_id: uuid.UUID, donnees: FenetreSaisie, request: Request,
                   principal: Principal = Depends(admin), session: Session = Depends(db)):
    s = _semestre(session, semestre_id)
    avant = {"debut": s.saisie_debut.isoformat() if s.saisie_debut else None,
             "fin": s.saisie_fin.isoformat() if s.saisie_fin else None}
    s.saisie_debut, s.saisie_fin = donnees.saisie_debut, donnees.saisie_fin
    tracer(session, request, "FENETRE_SAISIE_MODIFIEE", "SUCCES", acteur=principal, ressource="semestre",
           ressource_id=s.id, details={"avant": avant, "apres": {"debut": s.saisie_debut.isoformat(),
                                                                 "fin": s.saisie_fin.isoformat()}})
    session.commit()
    return vue_semestre(s)


@router.post("/semestres/{semestre_id}/fermeture")
def fermer_fenetre(semestre_id: uuid.UUID, request: Request, principal: Principal = Depends(admin),
                   session: Session = Depends(db)):
    s = _semestre(session, semestre_id)
    s.saisie_debut = s.saisie_fin = None
    tracer(session, request, "FENETRE_SAISIE_FERMEE", "SUCCES", acteur=principal, ressource="semestre", ressource_id=s.id)
    session.commit()
    return vue_semestre(s)


def _matiere(session: Session, matiere_id: uuid.UUID) -> Matiere:
    m = session.get(Matiere, matiere_id)
    if m is None:
        raise ErreurMetier(404, "Matière introuvable.", "INTROUVABLE")
    return m


def _etudiants_de_la_matiere(request: Request, session: Session, m: Matiere) -> list[str]:
    """Destinataires de la notification : la classe rattachée, à défaut les étudiants déjà notés."""
    if m.classe_id:
        try:
            return [e["id"] for e in classe(request, m.classe_id)["etudiants"] if e["statut"] == "ACTIF"]
        except ErreurMetier:
            pass
    return [str(i) for i in session.scalars(select(Note.etudiant_id).where(Note.matiere_id == m.id).distinct())]


@router.post("/matieres/{matiere_id}/publication")
def publier(matiere_id: uuid.UUID, request: Request, principal: Principal = Depends(admin),
            session: Session = Depends(db)):
    """Les notes deviennent visibles des étudiants et la matière est verrouillée."""
    m = _matiere(session, matiere_id)
    if m.publiee_le is not None:
        raise ErreurMetier(409, "Les notes de cette matière sont déjà publiées.", "DEJA_PUBLIEE")
    nombre = session.scalar(select(func.count()).select_from(Note).where(Note.matiere_id == m.id))
    if not nombre:
        raise ErreurMetier(409, "Aucune note à publier pour cette matière.", "AUCUNE_NOTE")
    m.publiee_le, m.publiee_par = maintenant(), principal.id
    tracer(session, request, "NOTES_PUBLIEES", "SUCCES", acteur=principal, ressource="matiere", ressource_id=m.id,
           details={"matiere": m.code, "notes": nombre})
    notifier(session, categorie="NOTES", titre="Nouvelles notes disponibles",
             message=f"Les notes de la matière « {m.libelle} » sont publiées.", lien="/notes",
             etudiants=_etudiants_de_la_matiere(request, session, m))
    session.commit()
    return {"id": str(m.id), "publiee_le": m.publiee_le.isoformat(), "notes": nombre}


@router.post("/matieres/{matiere_id}/depublication")
def depublier(matiere_id: uuid.UUID, donnees: Depublication, request: Request,
              principal: Principal = Depends(admin), session: Session = Depends(db)):
    """Retour exceptionnel en saisie (ex. rattrapage) : motif obligatoire, tracé dans l'audit."""
    m = _matiere(session, matiere_id)
    if m.publiee_le is None:
        raise ErreurMetier(409, "Les notes de cette matière ne sont pas publiées.", "NON_PUBLIEE")
    publiee = m.publiee_le.isoformat()
    m.publiee_le = m.publiee_par = None
    tracer(session, request, "NOTES_DEPUBLIEES", "ALERTE", acteur=principal, ressource="matiere", ressource_id=m.id,
           details={"matiere": m.code, "publiee_le": publiee, "motif": donnees.motif})
    session.commit()
    return {"id": str(m.id), "publiee_le": None}
