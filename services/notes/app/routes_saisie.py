"""F21 Saisie groupée par classe, F22 Statistiques d'une matière, F23 Exports Excel et PDF."""
import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, ENSEIGNANT, Principal, exiger_roles

from . import documents
from .models import HistoriqueNote, Matiere, Note
from .schemas import SaisieGroupee, TypeEvaluation
from .services import classe, controler_saisie, db, fmt, tracer, verifier_affectation, vue_semestre

router = APIRouter(prefix="/api/v1", tags=["saisie"])
enseignant = exiger_roles(ENSEIGNANT)
personnel = exiger_roles(ENSEIGNANT, ADMINISTRATEUR)
LIBELLES_TYPES = {"CONTROLE_CONTINU": "Contrôle continu", "EXAMEN": "Examen", "TP": "Travaux pratiques",
                  "RATTRAPAGE": "Rattrapage"}


def _matiere_autorisee(request: Request, session: Session, principal: Principal, matiere_id: uuid.UUID) -> Matiere:
    """L'enseignant n'accède qu'à ses matières affectées ; l'administrateur à toutes (lecture)."""
    if principal.role == ENSEIGNANT:
        return verifier_affectation(request, session, principal, matiere_id)
    m = session.get(Matiere, matiere_id)
    if m is None:
        raise ErreurMetier(404, "Matière introuvable.", "INTROUVABLE")
    return m


def _classe_de(request: Request, m: Matiere) -> dict:
    if m.classe_id is None:
        raise ErreurMetier(409, "Rattachez d'abord cette matière à une classe.", "SANS_CLASSE")
    return classe(request, m.classe_id)


@router.get("/matieres/{matiere_id}/grille")
def grille(matiere_id: uuid.UUID, request: Request, type_evaluation: TypeEvaluation,
           date_evaluation: date, principal: Principal = Depends(enseignant), session: Session = Depends(db)):
    """Liste de la classe avec la note déjà saisie pour cette évaluation, le cas échéant."""
    m = verifier_affectation(request, session, principal, matiere_id)
    c = _classe_de(request, m)
    existantes = {n.etudiant_id: n for n in session.scalars(select(Note).where(
        Note.matiere_id == m.id, Note.type_evaluation == type_evaluation, Note.date_evaluation == date_evaluation))}
    verrou = None
    try:
        controler_saisie(m)
    except ErreurMetier as e:
        verrou = {"code": e.code, "message": e.message}
    return {
        "matiere": {"id": str(m.id), "code": m.code, "libelle": m.libelle, "semestre": vue_semestre(m.semestre),
                    "publiee_le": m.publiee_le.isoformat() if m.publiee_le else None},
        "classe": {"id": c["id"], "code": c["code"], "libelle": c.get("libelle")},
        "saisie_possible": verrou is None, "verrou": verrou,
        "lignes": [{"etudiant": e, "note": ({"id": str(n.id), "valeur": fmt(n.valeur), "version": n.version}
                                            if (n := existantes.get(uuid.UUID(e["id"]))) else None)}
                   for e in c["etudiants"]],
    }


@router.post("/matieres/{matiere_id}/evaluations", status_code=201)
def saisir_evaluation(matiere_id: uuid.UUID, donnees: SaisieGroupee, request: Request,
                      principal: Principal = Depends(enseignant), session: Session = Depends(db)):
    """Tout ou rien : la moindre ligne invalide annule l'ensemble de la saisie."""
    m = verifier_affectation(request, session, principal, matiere_id)
    controler_saisie(m)
    membres = {e["id"]: e for e in _classe_de(request, m)["etudiants"]}
    hors_classe = [str(l.etudiant_id) for l in donnees.notes if str(l.etudiant_id) not in membres]
    if hors_classe:
        raise ErreurMetier(422, f"{len(hors_classe)} étudiant(s) n'appartiennent pas à cette classe.", "HORS_CLASSE")
    archives = [membres[str(l.etudiant_id)]["matricule"] for l in donnees.notes
                if membres[str(l.etudiant_id)]["statut"] != "ACTIF"]
    if archives:
        raise ErreurMetier(409, f"Étudiant(s) archivé(s) : {', '.join(archives)}.", "ETUDIANT_ARCHIVE")
    deja = session.scalars(select(Note.etudiant_id).where(
        Note.matiere_id == m.id, Note.type_evaluation == donnees.type_evaluation,
        Note.date_evaluation == donnees.date_evaluation,
        Note.etudiant_id.in_([l.etudiant_id for l in donnees.notes]))).all()
    if deja:
        raise ErreurMetier(409, f"{len(deja)} note(s) existent déjà pour cette évaluation ; "
                                "modifiez-les individuellement.", "DOUBLON")
    for ligne in donnees.notes:
        n = Note(etudiant_id=ligne.etudiant_id, matiere_id=m.id, valeur=ligne.valeur,
                 type_evaluation=donnees.type_evaluation, date_evaluation=donnees.date_evaluation,
                 saisie_par=principal.id, saisie_par_identifiant=principal.identifiant)
        session.add(n)
        session.flush()
        session.add(HistoriqueNote(note_id=n.id, ancienne_valeur=None, nouvelle_valeur=n.valeur,
                                   motif="Saisie initiale (grille de la classe)", modifie_par=principal.id,
                                   modifie_par_identifiant=principal.identifiant))
        # Chaque note reste tracée individuellement, comme une saisie unitaire (US23).
        tracer(session, request, "NOTE_AJOUTEE", "SUCCES", acteur=principal, ressource="note", ressource_id=n.id,
               details={"matiere": m.code, "etudiant": membres[str(ligne.etudiant_id)]["matricule"],
                        "valeur": fmt(n.valeur), "evaluation": n.type_evaluation,
                        "date": n.date_evaluation.isoformat(), "saisie": "groupee"})
    session.commit()
    return {"enregistrees": len(donnees.notes)}


def _notes(session: Session, m: Matiere) -> list[Note]:
    return session.scalars(select(Note).where(Note.matiere_id == m.id)
                           .order_by(Note.date_evaluation, Note.type_evaluation)).all()


@router.get("/matieres/{matiere_id}/statistiques")
def statistiques(matiere_id: uuid.UUID, request: Request, principal: Principal = Depends(personnel),
                 session: Session = Depends(db)):
    m = _matiere_autorisee(request, session, principal, matiere_id)
    notes = _notes(session, m)
    par_eval: dict[tuple, list] = defaultdict(list)
    par_etudiant: dict[uuid.UUID, list] = defaultdict(list)
    for n in notes:
        par_eval[(n.type_evaluation, n.date_evaluation)].append(n.valeur)
        par_etudiant[n.etudiant_id].append(n.valeur)
    moyennes = [sum(v) / len(v) for v in par_etudiant.values()]
    return {
        "matiere": {"id": str(m.id), "code": m.code, "libelle": m.libelle},
        "tranches": documents.LIBELLES_TRANCHES,
        "global": documents.statistiques(moyennes),
        "evaluations": [{"type_evaluation": t, "libelle": LIBELLES_TYPES[t], "date_evaluation": d.isoformat(),
                         **documents.statistiques(v)} for (t, d), v in sorted(par_eval.items(), key=lambda x: x[0][1])],
    }


@router.get("/matieres/{matiere_id}/export")
def exporter(matiere_id: uuid.UUID, request: Request, format: str = Query(pattern="^(xlsx|pdf)$"),
             principal: Principal = Depends(personnel), session: Session = Depends(db)):
    """Relevé de la matière ; chaque export est journalisé (données personnelles, R11)."""
    m = _matiere_autorisee(request, session, principal, matiere_id)
    notes = _notes(session, m)
    ids = list({str(n.etudiant_id) for n in notes})
    identites = {}
    for i in range(0, len(ids), 100):
        identites |= request.app.state.etudiants.post("/internal/etudiants/lot", json={"ids": ids[i:i + 100]}) or {}
    lignes = sorted(([identites.get(str(n.etudiant_id), {}).get("matricule", "?"),
                      identites.get(str(n.etudiant_id), {}).get("nom", "?"),
                      identites.get(str(n.etudiant_id), {}).get("prenom", "?"),
                      LIBELLES_TYPES[n.type_evaluation], n.date_evaluation.strftime("%d/%m/%Y"),
                      float(n.valeur)] for n in notes), key=lambda l: (l[1], l[2], l[4]))
    entetes = ["Matricule", "Nom", "Prénom", "Évaluation", "Date", "Note /20"]
    titre = f"{m.code} – {m.libelle}"
    tracer(session, request, "EXPORT_NOTES", "SUCCES", acteur=principal, ressource="matiere", ressource_id=m.id,
           details={"matiere": m.code, "format": format, "lignes": len(lignes)})
    session.commit()
    if format == "xlsx":
        contenu = documents.classeur(titre, entetes, lignes)
        type_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        stats = documents.statistiques([n.valeur for n in notes])
        resume = (f"{stats['nombre']} notes – moyenne {stats['moyenne'] if stats['moyenne'] is not None else '–'} – "
                  f"taux de réussite {stats['taux_reussite'] if stats['taux_reussite'] is not None else '–'} %")
        contenu = documents.pdf(documents.echapper(titre), documents.echapper(resume), [
            ("tableau", entetes, [l[:5] + [f"{l[5]:.2f}".replace(".", ",")] for l in lignes],
             [70, 110, 110, 100, 60, 50], (5,)),
        ])
        type_mime = "application/pdf"
    return Response(contenu, media_type=type_mime, headers={
        "Content-Disposition": f'attachment; filename="notes-{m.code}.{format}"'})
