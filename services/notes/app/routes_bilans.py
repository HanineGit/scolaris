"""F20 Relevé de notes vérifiable, F24 Synthèse de l'étudiant, F25 Tableau de bord, F26 Délibération."""
import hashlib
import json
import secrets
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from scolaris_common.calendrier import annee_academique
from scolaris_common.config import parametre
from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, ETUDIANT, Principal, exiger_roles

from . import documents
from .models import Matiere, Note, Reclamation, ReleveEmis, Semestre, maintenant
from .services import classe, db, db_lecture, fmt, tracer

router = APIRouter(prefix="/api/v1", tags=["bilans"])
etudiant = exiger_roles(ETUDIANT)
admin = exiger_roles(ADMINISTRATEUR)

SEUIL = Decimal("10")
MAX_RELEVES_PAR_JOUR = 10
CENTIEME = Decimal("0.01")


def _arrondi(v: Decimal) -> Decimal:
    return v.quantize(CENTIEME, ROUND_HALF_UP)


def moyennes_par_matiere(notes: list[Note]) -> dict[uuid.UUID, Decimal]:
    """Moyenne simple des évaluations d'une matière (même règle que la consultation mobile)."""
    groupes: dict[uuid.UUID, list[Decimal]] = defaultdict(list)
    for n in notes:
        groupes[n.matiere_id].append(n.valeur)
    return {m: _arrondi(sum(v) / len(v)) for m, v in groupes.items()}


def moyenne_ponderee(moyennes: dict[uuid.UUID, Decimal], matieres: dict[uuid.UUID, Matiere]) -> Decimal | None:
    coefs = sum(matieres[m].coefficient for m in moyennes)
    if not coefs:
        return None
    return _arrondi(sum(v * matieres[m].coefficient for m, v in moyennes.items()) / coefs)


def mention(moyenne: Decimal | None) -> str:
    if moyenne is None:
        return "–"
    for seuil, libelle in ((16, "Très bien"), (14, "Bien"), (12, "Assez bien"), (10, "Passable")):
        if moyenne >= seuil:
            return libelle
    return "Ajourné"


def _notes_publiees(session: Session, etudiant_id: uuid.UUID) -> list[Note]:
    return session.scalars(select(Note).join(Matiere).options(selectinload(Note.matiere).selectinload(Matiere.semestre))
                           .where(Note.etudiant_id == etudiant_id, Matiere.publiee_le.is_not(None))).all()


# --- F24 : synthèse de l'étudiant (tableau de bord mobile) ---

@router.get("/etudiants/moi/synthese")
def synthese(principal: Principal = Depends(etudiant), session: Session = Depends(db_lecture)):
    if principal.etudiant_id is None:
        raise ErreurMetier(403, "Accès refusé.", "ACCES_REFUSE")
    notes = _notes_publiees(session, principal.etudiant_id)
    matieres = {n.matiere_id: n.matiere for n in notes}
    moyennes = moyennes_par_matiere(notes)
    par_semestre: dict[tuple, dict] = defaultdict(dict)
    for m_id, v in moyennes.items():
        s = matieres[m_id].semestre
        par_semestre[(s.annee_academique, s.numero) if s else ("", 0)][m_id] = v
    evolution = [{"annee_academique": a, "numero": num, "libelle": f"S{num} {a}" if num else "Hors semestre",
                  "moyenne": fmt(moyenne_ponderee(ms, matieres))} for (a, num), ms in sorted(par_semestre.items())]
    generale = moyenne_ponderee(moyennes, matieres)
    a_surveiller = sorted(({"code": matieres[m].code, "libelle": matieres[m].libelle, "moyenne": fmt(v)}
                           for m, v in moyennes.items() if v < SEUIL), key=lambda x: x["moyenne"])
    ouvertes = session.scalar(select(func.count()).select_from(Reclamation).where(
        Reclamation.etudiant_id == principal.etudiant_id, Reclamation.statut.in_(("SOUMISE", "EN_COURS"))))
    publications = [m.publiee_le for m in matieres.values() if m.publiee_le]
    return {
        "moyenne_generale": fmt(generale), "mention": mention(generale),
        "matieres_validees": sum(v >= SEUIL for v in moyennes.values()), "matieres": len(moyennes),
        "evolution": evolution, "a_surveiller": a_surveiller, "reclamations_ouvertes": ouvertes,
        "derniere_publication": max(publications).isoformat() if publications else None,
    }


# --- F20 : relevé de notes PDF avec code de vérification ---

def _masquer(matricule: str) -> str:
    return matricule[:-2].rsplit("-", 1)[0] + "-**" + matricule[-2:]


@router.get("/etudiants/moi/releve")
def releve(request: Request, principal: Principal = Depends(etudiant), session: Session = Depends(db)):
    if principal.etudiant_id is None:
        raise ErreurMetier(403, "Accès refusé.", "ACCES_REFUSE")
    depuis = maintenant() - timedelta(days=1)
    emis = session.scalar(select(func.count()).select_from(ReleveEmis).where(
        ReleveEmis.etudiant_id == principal.etudiant_id, ReleveEmis.emis_le >= depuis))
    if emis >= MAX_RELEVES_PAR_JOUR:
        raise ErreurMetier(429, "Nombre maximal de relevés atteint pour aujourd'hui.", "LIMITE")
    identite = request.app.state.etudiants.get(f"/internal/etudiants/{principal.etudiant_id}")
    notes = _notes_publiees(session, principal.etudiant_id)
    matieres = {n.matiere_id: n.matiere for n in notes}
    moyennes = moyennes_par_matiere(notes)
    generale = moyenne_ponderee(moyennes, matieres)
    lignes = sorted(([m.semestre.libelle if m.semestre else "–", m.code, m.libelle, f"{m.coefficient:.1f}",
                      f"{moyennes[m_id]:.2f}".replace(".", ","), "Validée" if moyennes[m_id] >= SEUIL else "Non validée"]
                     for m_id, m in matieres.items()), key=lambda l: (l[0], l[1]))
    annee = annee_academique()
    code = secrets.token_hex(16)  # 128 bits : impossible à deviner
    canonique = json.dumps({"matricule": identite["matricule"], "annee": annee, "lignes": lignes,
                            "moyenne": fmt(generale)}, sort_keys=True, ensure_ascii=False)
    empreinte = hashlib.sha256(canonique.encode()).hexdigest()
    session.add(ReleveEmis(code=code, etudiant_id=principal.etudiant_id, matricule=identite["matricule"],
                           annee_academique=annee, moyenne_generale=generale, empreinte=empreinte))
    tracer(session, request, "RELEVE_EMIS", "SUCCES", acteur=principal, ressource="releve",
           details={"annee": annee, "matieres": len(lignes)})
    session.commit()
    # Adresse publique fixée par configuration : jamais déduite de l'en-tête Host (injection d'en-tête).
    url = f"{parametre('URL_PUBLIQUE', 'https://localhost:9443').rstrip('/')}/verification/{code}"
    e = documents.echapper
    bloc_qr = documents.bloc_verification(url, code, empreinte)
    contenu = documents.pdf("Relevé de notes", e(f"Année académique {annee}"), [
        ("texte", f"<b>{e(identite['nom'])} {e(identite['prenom'])}</b> – matricule {e(identite['matricule'])}"),
        ("espace", 8),
        ("tableau", ["Semestre", "Code", "Matière", "Coef.", "Moyenne", "Résultat"], lignes,
         [95, 55, 170, 40, 55, 70], (3, 4)),
        ("espace", 10),
        ("texte", f"Moyenne générale pondérée : <b>{e(fmt(generale) or '–').replace('.', ',')} / 20</b> – "
                  f"mention : <b>{e(mention(generale))}</b>"),
        ("espace", 18), bloc_qr,
        ("espace", 8),
        ("texte", "Seules les notes publiées figurent sur ce relevé. Document émis par voie électronique.", "petit"),
    ])
    return Response(contenu, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="releve-{identite["matricule"]}.pdf"',
                             # Code de vérification de ce relevé, pour l'afficher dans l'application.
                             "X-Code-Verification": code})


@router.get("/verification/{code}")
def verifier(code: str = Path(pattern=r"^[0-9a-f]{32}$"), session: Session = Depends(db)):
    """Route publique : confirme qu'un relevé a bien été émis, avec le strict minimum d'informations."""
    r = session.scalar(select(ReleveEmis).where(ReleveEmis.code == code))
    if r is None:
        return {"valide": False}
    return {"valide": True, "emis_le": r.emis_le.isoformat(), "annee_academique": r.annee_academique,
            "matricule": _masquer(r.matricule), "moyenne_generale": fmt(r.moyenne_generale), "empreinte": r.empreinte}


# --- F25 : indicateurs du tableau de bord de l'administrateur ---

@router.get("/notes/statistiques")
def indicateurs(principal: Principal = Depends(admin), session: Session = Depends(db)):
    aujourd_hui = date.today()
    debut = maintenant() - timedelta(days=13)
    par_jour = dict(session.execute(select(func.date(Note.saisie_le), func.count()).where(Note.saisie_le >= debut)
                                    .group_by(func.date(Note.saisie_le))).all())
    serie = [{"jour": (aujourd_hui - timedelta(days=i)).isoformat(),
              "notes": par_jour.get((aujourd_hui - timedelta(days=i)).isoformat(), 0)
              or par_jour.get(aujourd_hui - timedelta(days=i), 0)} for i in range(13, -1, -1)]
    matieres = session.scalars(select(Matiere).where(Matiere.active)).all()
    moyennes = dict(session.execute(select(Note.matiere_id, func.avg(Note.valeur)).group_by(Note.matiere_id)).all())
    ouvertes = session.scalar(select(func.count()).select_from(Reclamation).where(Reclamation.statut.in_(("SOUMISE", "EN_COURS"))))
    semestres = session.scalars(select(Semestre).where(Semestre.annee_academique == annee_academique())).all()
    return {
        "notes_total": session.scalar(select(func.count()).select_from(Note)),
        "notes_7_jours": sum(j["notes"] for j in serie[-7:]),
        "saisies_par_jour": serie,
        "matieres_actives": len(matieres), "matieres_publiees": sum(m.publiee_le is not None for m in matieres),
        "reclamations_ouvertes": ouvertes,
        "fenetres_ouvertes": [s.libelle for s in semestres if s.saisie_ouverte()],
        "moyennes_par_matiere": sorted(({"code": m.code, "libelle": m.libelle,
                                         "moyenne": round(float(moyennes[m.id]), 2)} for m in matieres if m.id in moyennes),
                                       key=lambda x: x["moyenne"]),
    }


# --- F26 : délibération d'une classe ---

@router.get("/classes/{classe_id}/deliberation")
def deliberation(classe_id: uuid.UUID, request: Request, semestre_id: uuid.UUID | None = None,
                 format: str = Query(default="json", pattern="^(json|pdf)$"),
                 principal: Principal = Depends(admin), session: Session = Depends(db)):
    c = classe(request, classe_id)
    requete = select(Matiere).where(Matiere.classe_id == classe_id)
    if semestre_id:
        requete = requete.where(Matiere.semestre_id == semestre_id)
    matieres = {m.id: m for m in session.scalars(requete.order_by(Matiere.code))}
    notes = session.scalars(select(Note).where(Note.matiere_id.in_(list(matieres)))).all() if matieres else []
    par_etudiant: dict[str, list[Note]] = defaultdict(list)
    for n in notes:
        par_etudiant[str(n.etudiant_id)].append(n)
    resultats = []
    for e in c["etudiants"]:
        moyennes = moyennes_par_matiere(par_etudiant.get(e["id"], []))
        generale = moyenne_ponderee(moyennes, matieres)
        resultats.append({"etudiant": e, "moyennes": {matieres[m].code: fmt(v) for m, v in moyennes.items()},
                          "moyenne_generale": fmt(generale), "mention": mention(generale),
                          "decision": "ADMIS" if generale is not None and generale >= SEUIL else
                                      ("AJOURNE" if generale is not None else "INCOMPLET")})
    classes_ = sorted((r for r in resultats if r["moyenne_generale"]), key=lambda r: Decimal(r["moyenne_generale"]), reverse=True)
    for rang, r in enumerate(classes_, start=1):
        r["rang"] = rang
    synthese_ = {"effectif": len(resultats), "admis": sum(r["decision"] == "ADMIS" for r in resultats),
                 "ajournes": sum(r["decision"] == "AJOURNE" for r in resultats),
                 "non_publiees": [m.code for m in matieres.values() if m.publiee_le is None]}
    if format == "json":
        return {"classe": {k: c[k] for k in ("id", "code", "libelle")},
                "matieres": [{"code": m.code, "libelle": m.libelle, "coefficient": f"{m.coefficient:.1f}",
                              "publiee": m.publiee_le is not None} for m in matieres.values()],
                "resultats": resultats, "synthese": synthese_}
    tracer(session, request, "DELIBERATION_EXPORTEE", "SUCCES", acteur=principal, ressource="classe",
           ressource_id=classe_id, details={"classe": c["code"], "effectif": len(resultats)})
    session.commit()
    codes = [m.code for m in matieres.values()]
    lignes = [[str(r.get("rang", "–")), r["etudiant"]["matricule"], f"{r['etudiant']['nom']} {r['etudiant']['prenom']}"]
              + [(r["moyennes"].get(code) or "–").replace(".", ",") for code in codes]
              + [(r["moyenne_generale"] or "–").replace(".", ","), r["decision"].capitalize()]
              for r in sorted(resultats, key=lambda r: r.get("rang", 10_000))]
    e = documents.echapper
    largeur_matiere = max(36, min(60, int(480 / max(len(codes), 1))))
    contenu = documents.pdf(
        e(f"Procès-verbal de délibération – {c['code']}"),
        e(f"{c.get('libelle') or ''} – effectif {synthese_['effectif']} – admis {synthese_['admis']} – "
          f"ajournés {synthese_['ajournes']}"),
        [("tableau", ["Rang", "Matricule", "Étudiant"] + codes + ["Moyenne", "Décision"], lignes,
          [32, 78, 150] + [largeur_matiere] * len(codes) + [52, 62], tuple(range(3, 4 + len(codes)))),
         ("espace", 12),
         ("texte", "Matières non publiées : " + e(", ".join(synthese_["non_publiees"]) or "aucune"), "petit"),
         ("espace", 30),
         ("texte", "Le président du jury : ____________________&nbsp;&nbsp;&nbsp;&nbsp; Date : ____ / ____ / ________")],
        paysage=True)
    return Response(contenu, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="deliberation-{c["code"]}.pdf"'})
