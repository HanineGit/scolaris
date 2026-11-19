"""Aides communes du service Notes : audit, contrôle d'affectation, présentation."""
import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from scolaris_common import audit
from scolaris_common.errors import ErreurMetier
from scolaris_common.security import Principal

from .models import Affectation, EvenementSortant, Matiere, Note, annee_academique

tracer = audit.Traceur("notes", EvenementSortant)


def db(request: Request):
    yield from request.app.state.bdd.session()


def db_lecture(request: Request):
    """Session ouverte avec le compte en lecture seule (consultation mobile F11)."""
    yield from request.app.state.bdd_lecture.session()


def refuser(request: Request, principal: Principal, session: Session, motif: str):
    """Refus journalisé (ACCES_REFUSE) : tentative hors des matières affectées (R16)."""
    tracer(session, request, "ACCES_REFUSE", "REFUSE", acteur=principal, ressource=request.url.path,
           details={"motif": motif})
    session.commit()
    raise ErreurMetier(403, "Accès refusé : cette matière ne vous est pas affectée.", "NON_AFFECTE")


def verifier_affectation(request: Request, session: Session, principal: Principal, matiere_id: uuid.UUID) -> Matiere:
    matiere = session.get(Matiere, matiere_id)
    if matiere is None:
        raise ErreurMetier(404, "Matière introuvable.", "INTROUVABLE")
    affecte = session.scalar(select(Affectation.id).where(
        Affectation.enseignant_id == principal.id, Affectation.matiere_id == matiere_id,
        Affectation.annee_academique == annee_academique()))
    if affecte is None:
        refuser(request, principal, session, "matiere_non_affectee")
    return matiere


def fmt(v) -> str | None:
    return None if v is None else f"{v:.2f}"


def vue_note(n: Note, etudiant: dict | None = None) -> dict:
    return {
        "id": str(n.id), "matiere_id": str(n.matiere_id), "matiere_code": n.matiere.code,
        "matiere_libelle": n.matiere.libelle, "etudiant_id": str(n.etudiant_id),
        "etudiant": etudiant, "type_evaluation": n.type_evaluation,
        "date_evaluation": n.date_evaluation.isoformat(), "valeur": fmt(n.valeur),
        "saisie_par": n.saisie_par_identifiant, "saisie_le": n.saisie_le.isoformat(),
        "modifie_le": n.modifie_le.isoformat() if n.modifie_le else None, "version": n.version,
    }


def controler_saisie(matiere: Matiere) -> None:
    """Saisie possible seulement avant publication et pendant la fenêtre ouverte du semestre (F17, F18)."""
    if not matiere.active:
        raise ErreurMetier(409, "Cette matière est désactivée.", "MATIERE_INACTIVE")
    if matiere.publiee_le is not None:
        raise ErreurMetier(409, "Les notes de cette matière sont publiées : elles ne se modifient plus "
                                "qu'à la suite d'une réclamation acceptée.", "NOTES_PUBLIEES")
    if matiere.semestre is not None and not matiere.semestre.saisie_ouverte():
        raise ErreurMetier(409, "La période de saisie de ce semestre est fermée.", "SAISIE_FERMEE")


def classe(request: Request, classe_id: uuid.UUID) -> dict:
    """Classe et liste de ses étudiants (identité minimale), lues dans le service Étudiants."""
    return request.app.state.etudiants.get(f"/internal/classes/{classe_id}")


def notifier(session: Session, **kw) -> None:
    audit.notifier(session, EvenementSortant, **kw)


def vue_semestre(s) -> dict | None:
    if s is None:
        return None
    return {"id": str(s.id), "annee_academique": s.annee_academique, "numero": s.numero, "libelle": s.libelle,
            "saisie_debut": s.saisie_debut.isoformat() if s.saisie_debut else None,
            "saisie_fin": s.saisie_fin.isoformat() if s.saisie_fin else None, "saisie_ouverte": s.saisie_ouverte()}
