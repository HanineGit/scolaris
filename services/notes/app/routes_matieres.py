"""F07 : matières et affectations (administrateur) ; « Mes matières » (enseignant)."""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, ENSEIGNANT, Principal, exiger_roles

from .models import Affectation, HistoriqueNote, Matiere, Note, Semestre, annee_academique
from .schemas import CreationMatiere, ModificationMatiere, NouvelleAffectation
from .services import classe, db, fmt, tracer, vue_semestre

router = APIRouter(prefix="/api/v1", tags=["matières"])
admin = exiger_roles(ADMINISTRATEUR)
enseignant = exiger_roles(ENSEIGNANT)


def _noms_enseignants(request: Request) -> dict[str, dict]:
    try:
        return {e["id"]: e for e in request.app.state.auth.get("/internal/comptes") or []}
    except ErreurMetier:
        return {}


def _vue(m: Matiere, noms: dict) -> dict:
    annee = annee_academique()
    return {
        "id": str(m.id), "code": m.code, "libelle": m.libelle, "coefficient": f"{m.coefficient:.1f}", "active": m.active,
        "classe_id": str(m.classe_id) if m.classe_id else None, "semestre": vue_semestre(m.semestre),
        "publiee_le": m.publiee_le.isoformat() if m.publiee_le else None,
        "enseignants": [
            {"affectation_id": str(a.id), "enseignant_id": str(a.enseignant_id),
             "nom": noms.get(str(a.enseignant_id), {}).get("nom"), "prenom": noms.get(str(a.enseignant_id), {}).get("prenom"),
             "depuis": a.cree_le.date().isoformat()}
            for a in m.affectations if a.annee_academique == annee
        ],
    }


def _rattachement(request: Request, session: Session, classe_id, semestre_id) -> None:
    """La classe doit exister dans le service Étudiants et le semestre dans ce service."""
    if classe_id is not None:
        try:
            classe(request, classe_id)
        except ErreurMetier as e:
            if e.statut == 404:
                raise ErreurMetier(422, "Classe introuvable.", "CLASSE")
            raise
    if semestre_id is not None and session.get(Semestre, semestre_id) is None:
        raise ErreurMetier(422, "Semestre introuvable.", "SEMESTRE")


def _matiere(session: Session, matiere_id: uuid.UUID) -> Matiere:
    m = session.get(Matiere, matiere_id)
    if m is None:
        raise ErreurMetier(404, "Matière introuvable.", "INTROUVABLE")
    return m


@router.get("/matieres")
def lister(request: Request, principal: Principal = Depends(admin), session: Session = Depends(db)):
    matieres = session.scalars(select(Matiere).options(selectinload(Matiere.affectations)).order_by(Matiere.code)).all()
    noms = _noms_enseignants(request)
    return {"annee_academique": annee_academique(), "elements": [_vue(m, noms) for m in matieres]}


@router.get("/matieres/enseignants-disponibles")
def enseignants_disponibles(request: Request, principal: Principal = Depends(admin)):
    return request.app.state.auth.get("/internal/comptes") or []


@router.post("/matieres", status_code=201)
def creer(donnees: CreationMatiere, request: Request, principal: Principal = Depends(admin),
          session: Session = Depends(db)):
    _rattachement(request, session, donnees.classe_id, donnees.semestre_id)
    m = Matiere(code=donnees.code, libelle=donnees.libelle, coefficient=donnees.coefficient,
                classe_id=donnees.classe_id, semestre_id=donnees.semestre_id)
    session.add(m)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Ce code de matière existe déjà.", "DOUBLON")
    tracer(session, request, "MATIERE_CREEE", "SUCCES", acteur=principal, ressource="matiere", ressource_id=m.id,
           details={"code": m.code, "classe_id": str(m.classe_id) if m.classe_id else None})
    session.commit()
    session.refresh(m)
    return _vue(m, {})


@router.patch("/matieres/{matiere_id}")
def modifier(matiere_id: uuid.UUID, donnees: ModificationMatiere, request: Request,
             principal: Principal = Depends(admin), session: Session = Depends(db)):
    """Pas de suppression : une matière est seulement désactivée (réponse « Éviter », R14)."""
    m = _matiere(session, matiere_id)
    _rattachement(request, session, donnees.classe_id, donnees.semestre_id)
    avant, apres = {}, {}
    for champ, valeur in donnees.model_dump(exclude_none=True).items():
        if valeur != getattr(m, champ):
            avant[champ], apres[champ] = str(getattr(m, champ)), str(valeur)
            setattr(m, champ, valeur)
    if apres:
        tracer(session, request, "MATIERE_MODIFIEE", "SUCCES", acteur=principal, ressource="matiere",
               ressource_id=m.id, details={"avant": avant, "apres": apres})
        session.commit()
    return _vue(m, _noms_enseignants(request))


@router.post("/matieres/{matiere_id}/affectations", status_code=201)
def affecter(matiere_id: uuid.UUID, donnees: NouvelleAffectation, request: Request,
             principal: Principal = Depends(admin), session: Session = Depends(db)):
    m = _matiere(session, matiere_id)
    if not m.active:
        raise ErreurMetier(409, "Impossible d'affecter une matière désactivée.", "MATIERE_INACTIVE")
    compte = request.app.state.auth.get(f"/internal/comptes/{donnees.enseignant_id}") or {}
    if compte.get("role") != "ENSEIGNANT" or compte.get("statut") != "ACTIF":
        raise ErreurMetier(422, "Ce compte n'est pas un enseignant actif.", "PAS_ENSEIGNANT")
    a = Affectation(enseignant_id=donnees.enseignant_id, matiere_id=m.id, annee_academique=annee_academique(),
                    cree_par=principal.id)
    session.add(a)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Cet enseignant est déjà affecté à cette matière.", "DOUBLON")
    tracer(session, request, "AFFECTATION_AJOUTEE", "SUCCES", acteur=principal, ressource="matiere",
           ressource_id=m.id, details={"enseignant_id": str(donnees.enseignant_id), "annee": a.annee_academique})
    session.commit()
    return {"affectation_id": str(a.id)}


@router.delete("/matieres/{matiere_id}/affectations/{affectation_id}", status_code=204)
def retirer(matiere_id: uuid.UUID, affectation_id: uuid.UUID, request: Request,
            principal: Principal = Depends(admin), session: Session = Depends(db)):
    """Le retrait d'une affectation n'efface aucune note déjà saisie."""
    a = session.get(Affectation, affectation_id)
    if a is None or a.matiere_id != matiere_id:
        raise ErreurMetier(404, "Affectation introuvable.", "INTROUVABLE")
    tracer(session, request, "AFFECTATION_RETIREE", "SUCCES", acteur=principal, ressource="matiere",
           ressource_id=matiere_id, details={"enseignant_id": str(a.enseignant_id), "annee": a.annee_academique})
    session.delete(a)
    session.commit()


@router.get("/enseignants/moi/matieres")
def mes_matieres(principal: Principal = Depends(enseignant), session: Session = Depends(db)):
    annee = annee_academique()
    matieres = session.scalars(select(Matiere).join(Affectation).where(
        Affectation.enseignant_id == principal.id, Affectation.annee_academique == annee).order_by(Matiere.code)).all()
    elements = []
    for m in matieres:
        nb = session.scalar(select(func.count()).select_from(Note).where(Note.matiere_id == m.id))
        derniere = session.execute(select(Note.type_evaluation, Note.date_evaluation).where(Note.matiere_id == m.id)
                                   .order_by(Note.date_evaluation.desc()).limit(1)).first()
        modifiees = session.scalar(select(func.count(func.distinct(HistoriqueNote.note_id))).join(Note)
                                   .where(Note.matiere_id == m.id, HistoriqueNote.ancienne_valeur.is_not(None)))
        elements.append({
            "id": str(m.id), "code": m.code, "libelle": m.libelle, "coefficient": f"{m.coefficient:.1f}",
            "active": m.active, "notes_saisies": nb, "notes_modifiees": modifiees,
            "classe_id": str(m.classe_id) if m.classe_id else None, "semestre": vue_semestre(m.semestre),
            "publiee_le": m.publiee_le.isoformat() if m.publiee_le else None,
            "derniere_evaluation": {"type": derniere[0], "date": derniere[1].isoformat()} if derniere else None,
        })
    return {"annee_academique": annee, "elements": elements}
