"""F19 Réclamations : contestation d'une note publiée et traitement par l'enseignant."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from scolaris_common.calendrier import annee_academique
from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, ENSEIGNANT, ETUDIANT, Principal, exiger_roles

from .models import Affectation, HistoriqueNote, Matiere, Note, Reclamation, maintenant
from .schemas import NouvelleReclamation, TraitementReclamation
from .services import db, db_lecture, fmt, notifier, tracer, verifier_affectation

router = APIRouter(prefix="/api/v1", tags=["réclamations"])
etudiant = exiger_roles(ETUDIANT)
enseignant = exiger_roles(ENSEIGNANT)
admin = exiger_roles(ADMINISTRATEUR)

DELAI_JOURS = 15          # après la publication des notes de la matière
MAX_OUVERTES = 5          # par étudiant, contre les dépôts en masse
OUVERTES = ("SOUMISE", "EN_COURS")


def _vue(r: Reclamation, etudiant: dict | None = None) -> dict:
    n = r.note
    return {
        "id": str(r.id), "statut": r.statut, "motif": r.motif, "reponse": r.reponse,
        "soumise_le": r.soumise_le.isoformat(), "traitee_le": r.traitee_le.isoformat() if r.traitee_le else None,
        "traitee_par": r.traitee_par_identifiant, "version": r.version, "etudiant": etudiant,
        "note": {"id": str(n.id), "valeur": fmt(n.valeur), "type_evaluation": n.type_evaluation,
                 "date_evaluation": n.date_evaluation.isoformat(), "matiere_code": n.matiere.code,
                 "matiere_libelle": n.matiere.libelle, "version": n.version},
    }


def _requete():
    return select(Reclamation).options(selectinload(Reclamation.note).selectinload(Note.matiere))


# --- Étudiant ---

@router.post("/etudiants/moi/reclamations", status_code=201)
def deposer(donnees: NouvelleReclamation, request: Request, principal: Principal = Depends(etudiant),
            session: Session = Depends(db)):
    if principal.etudiant_id is None:
        raise ErreurMetier(403, "Accès refusé.", "ACCES_REFUSE")
    n = session.get(Note, donnees.note_id)
    # Même réponse qu'une note inexistante : on ne révèle pas l'existence des notes des autres (R20).
    if n is None or n.etudiant_id != principal.etudiant_id or n.matiere.publiee_le is None:
        raise ErreurMetier(404, "Note introuvable.", "INTROUVABLE")
    if maintenant() > n.matiere.publiee_le + timedelta(days=DELAI_JOURS):
        raise ErreurMetier(409, f"Le délai de réclamation ({DELAI_JOURS} jours après publication) est dépassé.",
                           "DELAI_DEPASSE")
    if session.scalar(select(Reclamation.id).where(Reclamation.note_id == n.id, Reclamation.statut.in_(OUVERTES))):
        raise ErreurMetier(409, "Une réclamation est déjà en cours pour cette note.", "DEJA_OUVERTE")
    ouvertes = session.scalar(select(func.count()).select_from(Reclamation).where(
        Reclamation.etudiant_id == principal.etudiant_id, Reclamation.statut.in_(OUVERTES)))
    if ouvertes >= MAX_OUVERTES:
        raise ErreurMetier(409, f"Vous avez déjà {MAX_OUVERTES} réclamations en cours.", "LIMITE")
    r = Reclamation(note_id=n.id, etudiant_id=principal.etudiant_id, motif=donnees.motif)
    session.add(r)
    session.flush()
    tracer(session, request, "RECLAMATION_SOUMISE", "SUCCES", acteur=principal, ressource="reclamation",
           ressource_id=r.id, details={"note_id": str(n.id), "matiere": n.matiere.code})
    enseignants = session.scalars(select(Affectation.enseignant_id).where(
        Affectation.matiere_id == n.matiere_id, Affectation.annee_academique == annee_academique()))
    notifier(session, categorie="RECLAMATION", titre="Nouvelle réclamation",
             message=f"Une réclamation a été déposée en {n.matiere.libelle}.", lien="/enseignant/reclamations",
             utilisateurs=list(enseignants))
    session.commit()
    session.refresh(r)
    return _vue(r)


@router.get("/etudiants/moi/reclamations")
def mes_reclamations(principal: Principal = Depends(etudiant), session: Session = Depends(db_lecture)):
    if principal.etudiant_id is None:
        raise ErreurMetier(403, "Accès refusé.", "ACCES_REFUSE")
    lignes = session.scalars(_requete().where(Reclamation.etudiant_id == principal.etudiant_id)
                             .order_by(Reclamation.soumise_le.desc())).all()
    return {"delai_jours": DELAI_JOURS, "elements": [_vue(r) for r in lignes]}


# --- Enseignant ---

def _identites(request: Request, ids) -> dict:
    ids = list({str(i) for i in ids})[:100]
    if not ids:
        return {}
    try:
        return request.app.state.etudiants.post("/internal/etudiants/lot", json={"ids": ids}) or {}
    except ErreurMetier:
        return {}


@router.get("/enseignants/moi/reclamations")
def a_traiter(request: Request, statut: str | None = Query(default=None, pattern="^(SOUMISE|EN_COURS|ACCEPTEE|REJETEE)$"),
              principal: Principal = Depends(enseignant), session: Session = Depends(db)):
    matieres = select(Affectation.matiere_id).where(Affectation.enseignant_id == principal.id,
                                                    Affectation.annee_academique == annee_academique())
    requete = _requete().join(Note).where(Note.matiere_id.in_(matieres))
    if statut:
        requete = requete.where(Reclamation.statut == statut)
    lignes = session.scalars(requete.order_by(Reclamation.soumise_le.desc()).limit(200)).all()
    identites = _identites(request, [r.etudiant_id for r in lignes])
    return {"elements": [_vue(r, identites.get(str(r.etudiant_id))) for r in lignes]}


@router.put("/reclamations/{reclamation_id}")
def traiter(reclamation_id: uuid.UUID, donnees: TraitementReclamation, request: Request,
            principal: Principal = Depends(enseignant), session: Session = Depends(db)):
    r = session.get(Reclamation, reclamation_id)
    if r is None:
        raise ErreurMetier(404, "Réclamation introuvable.", "INTROUVABLE")
    n = r.note
    verifier_affectation(request, session, principal, n.matiere_id)
    if r.statut not in OUVERTES:
        raise ErreurMetier(409, "Cette réclamation est déjà close.", "CLOSE")
    if donnees.version != r.version:
        raise ErreurMetier(409, "La réclamation a été modifiée entre-temps. Rechargez-la.", "VERSION")
    r.statut, r.reponse = donnees.decision, donnees.reponse
    r.traitee_par, r.traitee_par_identifiant = principal.id, principal.identifiant
    if donnees.decision != "EN_COURS":
        r.traitee_le = maintenant()
    if donnees.decision == "ACCEPTEE":
        if donnees.nouvelle_valeur == n.valeur:
            raise ErreurMetier(422, "La nouvelle note est identique à la note actuelle.", "INCHANGEE")
        # Seule voie de modification d'une note publiée : tracée dans l'historique et l'audit.
        ancienne = n.valeur
        n.valeur, n.modifie_le = donnees.nouvelle_valeur, maintenant()
        motif = f"Réclamation acceptée : {donnees.reponse}"[:255]
        session.add(HistoriqueNote(note_id=n.id, ancienne_valeur=ancienne, nouvelle_valeur=n.valeur, motif=motif,
                                   modifie_par=principal.id, modifie_par_identifiant=principal.identifiant))
        tracer(session, request, "NOTE_MODIFIEE", "SUCCES", acteur=principal, ressource="note", ressource_id=n.id,
               details={"matiere": n.matiere.code, "etudiant_id": str(n.etudiant_id), "avant": fmt(ancienne),
                        "apres": fmt(n.valeur), "motif": motif, "reclamation_id": str(r.id)})
    try:
        session.flush()
    except StaleDataError:
        session.rollback()
        raise ErreurMetier(409, "La réclamation a été modifiée entre-temps. Rechargez-la.", "VERSION")
    tracer(session, request, "RECLAMATION_TRAITEE", "SUCCES", acteur=principal, ressource="reclamation",
           ressource_id=r.id, details={"decision": r.statut, "matiere": n.matiere.code})
    libelles = {"EN_COURS": "est en cours d'examen", "ACCEPTEE": "a été acceptée", "REJETEE": "a été rejetée"}
    notifier(session, categorie="RECLAMATION", titre="Suivi de votre réclamation",
             message=f"Votre réclamation en {n.matiere.libelle} {libelles[r.statut]}.", lien="/reclamations",
             etudiants=[r.etudiant_id])
    session.commit()
    return _vue(r)


# --- Administrateur : vue d'ensemble ---

@router.get("/reclamations")
def toutes(request: Request, statut: str | None = Query(default=None, pattern="^(SOUMISE|EN_COURS|ACCEPTEE|REJETEE)$"),
           principal: Principal = Depends(admin), session: Session = Depends(db)):
    requete = _requete()
    if statut:
        requete = requete.where(Reclamation.statut == statut)
    lignes = session.scalars(requete.order_by(Reclamation.soumise_le.desc()).limit(200)).all()
    identites = _identites(request, [r.etudiant_id for r in lignes])
    return {"elements": [_vue(r, identites.get(str(r.etudiant_id))) for r in lignes]}
