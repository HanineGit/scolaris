"""F08 Enregistrement, F09 Consultation, F10 Modification des notes ; F11 consultation mobile."""
import uuid
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, ENSEIGNANT, ETUDIANT, Principal, exiger_roles

from .models import HistoriqueNote, Matiere, Note, maintenant
from .schemas import ModificationNote, NouvelleNote, TypeEvaluation
from .services import controler_saisie, db, db_lecture, fmt, refuser, tracer, verifier_affectation, vue_note

router = APIRouter(prefix="/api/v1", tags=["notes"])
enseignant = exiger_roles(ENSEIGNANT)
admin = exiger_roles(ADMINISTRATEUR)
enseignant_ou_admin = exiger_roles(ENSEIGNANT, ADMINISTRATEUR)
etudiant = exiger_roles(ETUDIANT)


def _etudiants(request: Request, ids) -> dict:
    ids = list({str(i) for i in ids})[:100]
    if not ids:
        return {}
    try:
        return request.app.state.etudiants.post("/internal/etudiants/lot", json={"ids": ids}) or {}
    except ErreurMetier:
        return {}


@router.get("/notes/etudiant")
def rechercher_etudiant(request: Request, matricule: str = Query(pattern=r"^ETU-\d{4}-\d{4}$"),
                        principal: Principal = Depends(enseignant)):
    """Vérification visuelle de l'étudiant avant saisie (R15) : identité minimale uniquement."""
    e = request.app.state.etudiants.get(f"/internal/etudiants?matricule={matricule}")
    return {k: e[k] for k in ("id", "matricule", "nom", "prenom", "statut")}


@router.post("/notes", status_code=201)
def enregistrer(donnees: NouvelleNote, request: Request, principal: Principal = Depends(enseignant),
                session: Session = Depends(db)):
    matiere = verifier_affectation(request, session, principal, donnees.matiere_id)
    controler_saisie(matiere)
    etu = request.app.state.etudiants.get(f"/internal/etudiants/{donnees.etudiant_id}")
    if etu.get("statut") != "ACTIF":
        raise ErreurMetier(409, "Impossible de noter un étudiant archivé.", "ETUDIANT_ARCHIVE")
    n = Note(etudiant_id=donnees.etudiant_id, matiere_id=matiere.id, valeur=donnees.valeur,
             type_evaluation=donnees.type_evaluation, date_evaluation=donnees.date_evaluation,
             saisie_par=principal.id, saisie_par_identifiant=principal.identifiant)
    session.add(n)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Une note existe déjà pour cette évaluation et cet étudiant.", "DOUBLON")
    session.add(HistoriqueNote(note_id=n.id, ancienne_valeur=None, nouvelle_valeur=n.valeur, motif="Saisie initiale",
                               modifie_par=principal.id, modifie_par_identifiant=principal.identifiant))
    tracer(session, request, "NOTE_AJOUTEE", "SUCCES", acteur=principal, ressource="note", ressource_id=n.id,
           details={"matiere": matiere.code, "etudiant": etu.get("matricule"), "valeur": fmt(n.valeur),
                    "evaluation": n.type_evaluation, "date": n.date_evaluation.isoformat()})
    session.commit()
    return vue_note(n, {k: etu[k] for k in ("matricule", "nom", "prenom")})


@router.get("/matieres/{matiere_id}/notes")
def notes_de_la_matiere(
    matiere_id: uuid.UUID, request: Request,
    type_evaluation: TypeEvaluation | None = None, du: date | None = None, au: date | None = None,
    date_evaluation: date | None = None,
    matricule: str | None = Query(default=None, pattern=r"^ETU-\d{4}-\d{4}$"),
    page: int = Query(default=1, ge=1, le=10_000), taille: int = Query(default=20, ge=1, le=50),
    principal: Principal = Depends(enseignant), session: Session = Depends(db),
):
    verifier_affectation(request, session, principal, matiere_id)
    requete = select(Note).options(selectinload(Note.matiere)).where(Note.matiere_id == matiere_id)
    if type_evaluation:
        requete = requete.where(Note.type_evaluation == type_evaluation)
    if date_evaluation:
        requete = requete.where(Note.date_evaluation == date_evaluation)
    if du:
        requete = requete.where(Note.date_evaluation >= du)
    if au:
        requete = requete.where(Note.date_evaluation <= au)
    if matricule:
        try:
            etu = request.app.state.etudiants.get(f"/internal/etudiants?matricule={matricule}")
            requete = requete.where(Note.etudiant_id == uuid.UUID(etu["id"]))
        except ErreurMetier as e:
            if e.statut != 404:
                raise
            return {"total": 0, "page": page, "elements": []}
    total = session.scalar(select(func.count()).select_from(requete.subquery()))
    notes = session.scalars(requete.order_by(Note.date_evaluation.desc(), Note.saisie_le.desc())
                            .offset((page - 1) * taille).limit(taille)).all()
    etudiants = _etudiants(request, [n.etudiant_id for n in notes])
    return {"total": total, "page": page,
            "elements": [vue_note(n, etudiants.get(str(n.etudiant_id))) for n in notes]}


@router.get("/notes")
def notes_d_un_etudiant(etudiant: uuid.UUID, principal: Principal = Depends(admin), session: Session = Depends(db)):
    """Lecture seule pour la fiche étudiant de l'administrateur (F05/F09)."""
    notes = session.scalars(select(Note).options(selectinload(Note.matiere)).where(Note.etudiant_id == etudiant)
                            .order_by(Note.date_evaluation.desc())).all()
    return {"elements": [vue_note(n) for n in notes]}


@router.put("/notes/{note_id}")
def modifier(note_id: uuid.UUID, donnees: ModificationNote, request: Request,
             principal: Principal = Depends(enseignant), session: Session = Depends(db)):
    n = session.get(Note, note_id)
    if n is None:
        raise ErreurMetier(404, "Note introuvable.", "INTROUVABLE")
    verifier_affectation(request, session, principal, n.matiere_id)
    controler_saisie(n.matiere)
    if donnees.version != n.version:
        raise ErreurMetier(409, "La note a été modifiée entre-temps. Rechargez-la.", "VERSION")
    if donnees.valeur == n.valeur:
        raise ErreurMetier(422, "La nouvelle valeur est identique à la valeur actuelle.", "INCHANGEE")
    ancienne = n.valeur
    n.valeur, n.modifie_le = donnees.valeur, maintenant()
    # Note et historique sont écrits dans la même transaction (R18).
    session.add(HistoriqueNote(note_id=n.id, ancienne_valeur=ancienne, nouvelle_valeur=donnees.valeur,
                               motif=donnees.motif, modifie_par=principal.id,
                               modifie_par_identifiant=principal.identifiant))
    try:
        session.flush()
    except StaleDataError:
        session.rollback()
        raise ErreurMetier(409, "La note a été modifiée entre-temps. Rechargez-la.", "VERSION")
    tracer(session, request, "NOTE_MODIFIEE", "SUCCES", acteur=principal, ressource="note", ressource_id=n.id,
           details={"matiere": n.matiere.code, "etudiant_id": str(n.etudiant_id), "avant": fmt(ancienne),
                    "apres": fmt(donnees.valeur), "motif": donnees.motif})
    session.commit()
    return vue_note(n)


@router.get("/notes/{note_id}/historique")
def historique(note_id: uuid.UUID, request: Request, principal: Principal = Depends(enseignant_ou_admin),
               session: Session = Depends(db)):
    n = session.get(Note, note_id)
    if n is None:
        raise ErreurMetier(404, "Note introuvable.", "INTROUVABLE")
    if principal.role == ENSEIGNANT:
        verifier_affectation(request, session, principal, n.matiere_id)
    return {"elements": [
        {"date": h.modifie_le.isoformat(), "auteur": h.modifie_par_identifiant, "avant": fmt(h.ancienne_valeur),
         "apres": fmt(h.nouvelle_valeur), "motif": h.motif}
        for h in sorted(n.historique, key=lambda h: h.modifie_le, reverse=True)
    ]}


@router.get("/etudiants/moi/notes")
def mes_notes(
    request: Request, matiere: str | None = Query(default=None, pattern=r"^[A-Z0-9]{2,10}$"),
    du: date | None = None, au: date | None = None,
    principal: Principal = Depends(etudiant), session: Session = Depends(db_lecture),
):
    """F11 : l'identité vient exclusivement du jeton ; aucun identifiant n'est accepté du client (R20)."""
    if principal.etudiant_id is None:
        raise ErreurMetier(403, "Accès refusé.", "ACCES_REFUSE")
    # Seules les notes des matières publiées sont visibles (F18).
    requete = (select(Note).join(Matiere).options(selectinload(Note.matiere))
               .where(Note.etudiant_id == principal.etudiant_id, Matiere.publiee_le.is_not(None)))
    if matiere:
        requete = requete.where(Matiere.code == matiere)
    if du:
        requete = requete.where(Note.date_evaluation >= du)
    if au:
        requete = requete.where(Note.date_evaluation <= au)
    notes = session.scalars(requete.order_by(Note.date_evaluation.desc())).all()

    par_matiere: dict[uuid.UUID, list[Note]] = defaultdict(list)
    for n in notes:
        par_matiere[n.matiere_id].append(n)
    matieres, somme, coefs = [], Decimal(0), Decimal(0)
    for liste in par_matiere.values():
        m = liste[0].matiere
        moyenne = (sum(n.valeur for n in liste) / len(liste)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        somme += moyenne * m.coefficient
        coefs += m.coefficient
        matieres.append({"code": m.code, "libelle": m.libelle, "coefficient": f"{m.coefficient:.1f}",
                         "moyenne": fmt(moyenne), "nombre_notes": len(liste),
                         "derniere_date": liste[0].date_evaluation.isoformat()})
    generale = (somme / coefs).quantize(Decimal("0.01"), ROUND_HALF_UP) if coefs else None
    return {
        "moyenne_generale": fmt(generale),
        "matieres": sorted(matieres, key=lambda m: m["libelle"]),
        "notes": [{"id": str(n.id), "matiere_code": n.matiere.code, "matiere_libelle": n.matiere.libelle,
                   "type_evaluation": n.type_evaluation, "date_evaluation": n.date_evaluation.isoformat(),
                   "valeur": fmt(n.valeur), "modifiee_le": n.modifie_le.date().isoformat() if n.modifie_le else None}
                  for n in notes],
    }
