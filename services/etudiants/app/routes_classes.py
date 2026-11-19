"""F15 Classes et inscriptions, F16 Import d'une promotion, indicateurs de scolarité."""
import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from scolaris_common.calendrier import annee_academique
from scolaris_common.errors import ErreurMetier
from scolaris_common.security import Principal, exiger_service

from .models import Classe, Etudiant
from .routes import _charger, _resume, _vue, admin, classe_ouverte, creer_etudiant, db, tracer
from .schemas import CreationClasse, CreationEtudiant, EtudiantVue, Inscription, ModificationClasse

classes = APIRouter(prefix="/api/v1/classes", tags=["classes"])
scolarite = APIRouter(prefix="/api/v1/etudiants", tags=["étudiants"])
interne_classes = APIRouter(prefix="/internal/classes", include_in_schema=False,
                            dependencies=[Depends(exiger_service("service_token_notes"))])

MAX_LIGNES_IMPORT = 1000
COLONNES = ("nom", "prenom", "email")


def _vue_classe(c: Classe, effectif: int = 0) -> dict:
    return {"id": str(c.id), "code": c.code, "libelle": c.libelle, "filiere": c.filiere, "niveau": c.niveau,
            "annee_academique": c.annee_academique, "active": c.active, "effectif": effectif}


def _classe(session: Session, classe_id: uuid.UUID) -> Classe:
    c = session.get(Classe, classe_id)
    if c is None:
        raise ErreurMetier(404, "Classe introuvable.", "INTROUVABLE")
    return c


def _effectifs(session: Session) -> dict:
    return dict(session.execute(select(Etudiant.classe_id, func.count()).where(Etudiant.statut == "ACTIF")
                                .group_by(Etudiant.classe_id)).all())


# --- Classes ---

@classes.get("")
def lister_classes(annee: str | None = Query(default=None, pattern=r"^\d{4}-\d{4}$"),
                   principal: Principal = Depends(admin), session: Session = Depends(db)):
    annee = annee or annee_academique()
    lignes = session.scalars(select(Classe).where(Classe.annee_academique == annee)
                             .order_by(Classe.niveau, Classe.code)).all()
    effectifs = _effectifs(session)
    return {"annee_academique": annee, "elements": [_vue_classe(c, effectifs.get(c.id, 0)) for c in lignes]}


@classes.post("", status_code=201)
def creer_classe(donnees: CreationClasse, request: Request, principal: Principal = Depends(admin),
                 session: Session = Depends(db)):
    c = Classe(**donnees.model_dump(), cree_par=principal.id)
    session.add(c)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Ce code de classe existe déjà pour cette année.", "DOUBLON")
    tracer(session, request, "CLASSE_CREEE", "SUCCES", acteur=principal, ressource="classe", ressource_id=c.id,
           details={"code": c.code, "annee": c.annee_academique})
    session.commit()
    return _vue_classe(c)


@classes.patch("/{classe_id}")
def modifier_classe(classe_id: uuid.UUID, donnees: ModificationClasse, request: Request,
                    principal: Principal = Depends(admin), session: Session = Depends(db)):
    c = _classe(session, classe_id)
    avant, apres = {}, {}
    for champ, valeur in donnees.model_dump(exclude_none=True).items():
        if getattr(c, champ) != valeur:
            avant[champ], apres[champ] = getattr(c, champ), valeur
            setattr(c, champ, valeur)
    if apres:
        tracer(session, request, "CLASSE_MODIFIEE", "SUCCES", acteur=principal, ressource="classe",
               ressource_id=c.id, details={"avant": avant, "apres": apres})
        session.commit()
    return _vue_classe(c, _effectifs(session).get(c.id, 0))


# --- Inscription d'un étudiant dans une classe ---

@scolarite.put("/{etudiant_id}/classe", response_model=EtudiantVue)
def inscrire(etudiant_id: uuid.UUID, donnees: Inscription, request: Request,
             principal: Principal = Depends(admin), session: Session = Depends(db)):
    e = _charger(session, etudiant_id)
    if e.statut == "ARCHIVE":
        raise ErreurMetier(409, "Un étudiant archivé ne peut plus être inscrit.", "ARCHIVE")
    if donnees.version != e.version:
        raise ErreurMetier(409, "La fiche a été modifiée entre-temps. Rechargez-la.", "VERSION")
    nouvelle = classe_ouverte(session, donnees.classe_id)
    avant = e.classe.code if e.classe else None
    e.classe = nouvelle
    try:
        session.flush()
    except StaleDataError:
        session.rollback()
        raise ErreurMetier(409, "La fiche a été modifiée entre-temps. Rechargez-la.", "VERSION")
    tracer(session, request, "ETUDIANT_INSCRIT", "SUCCES", acteur=principal, ressource="etudiant", ressource_id=e.id,
           details={"avant": {"classe": avant}, "apres": {"classe": nouvelle.code if nouvelle else None}})
    session.commit()
    return _vue(e)


# --- Indicateurs du tableau de bord ---

@scolarite.get("/statistiques")
def statistiques(principal: Principal = Depends(admin), session: Session = Depends(db)):
    statuts = dict(session.execute(select(Etudiant.statut, func.count()).group_by(Etudiant.statut)).all())
    sans_classe = session.scalar(select(func.count()).select_from(Etudiant)
                                 .where(Etudiant.statut == "ACTIF", Etudiant.classe_id.is_(None)))
    annee = annee_academique()
    effectifs = _effectifs(session)
    par_classe = [{"code": c.code, "libelle": c.libelle, "effectif": effectifs.get(c.id, 0)}
                  for c in session.scalars(select(Classe).where(Classe.annee_academique == annee, Classe.active)
                                           .order_by(Classe.niveau, Classe.code))]
    return {"actifs": statuts.get("ACTIF", 0), "archives": statuts.get("ARCHIVE", 0), "sans_classe": sans_classe,
            "annee_academique": annee, "par_classe": par_classe}


# --- F16 : import d'une promotion depuis un fichier CSV ---

class DemandeImport(BaseModel):
    contenu: str = Field(max_length=1_000_000)  # 1 Mo au plus (R11 : pas de traitement massif)
    classe_id: uuid.UUID | None = None
    confirmer: bool = False


def _lire_csv(contenu: str) -> list[dict]:
    texte = contenu.lstrip("﻿")
    try:
        dialecte = csv.Sniffer().sniff(texte.splitlines()[0] if texte else "", delimiters=";,")
    except csv.Error:
        dialecte = csv.excel
    lecteur = csv.DictReader(io.StringIO(texte), dialect=dialecte)
    entetes = [(h or "").strip().lower() for h in (lecteur.fieldnames or [])]
    if not set(COLONNES) <= set(entetes):
        raise ErreurMetier(422, "Colonnes attendues : nom, prenom, email.", "FORMAT")
    lignes = []
    for brute in lecteur:
        lignes.append({(k or "").strip().lower(): (v or "").strip() for k, v in brute.items() if k})
        if len(lignes) > MAX_LIGNES_IMPORT:
            raise ErreurMetier(422, f"Un import compte au plus {MAX_LIGNES_IMPORT} lignes.", "TROP_DE_LIGNES")
    if not lignes:
        raise ErreurMetier(422, "Le fichier ne contient aucune ligne.", "VIDE")
    return lignes


@scolarite.post("/import")
def importer(donnees: DemandeImport, request: Request, principal: Principal = Depends(admin),
             session: Session = Depends(db)):
    """Vérification ligne par ligne d'abord ; l'enregistrement n'a lieu que si aucune ligne n'est en erreur."""
    classe = classe_ouverte(session, donnees.classe_id)
    lignes = _lire_csv(donnees.contenu)
    existants = set(session.scalars(select(Etudiant.email).where(
        Etudiant.email.in_([l.get("email", "").lower() for l in lignes]))))
    vus: set[str] = set()
    rapport, valides = [], []
    for numero, ligne in enumerate(lignes, start=2):  # ligne 1 : en-têtes
        erreurs = []
        try:
            v = CreationEtudiant(nom=ligne.get("nom", ""), prenom=ligne.get("prenom", ""), email=ligne.get("email", ""))
        except ValidationError as ex:
            v = None
            erreurs = sorted({str(e["loc"][0]) for e in ex.errors()})
            erreurs = [f"{champ} invalide" for champ in erreurs]
        if v:
            if v.email in existants:
                erreurs.append("adresse déjà utilisée")
            elif v.email in vus:
                erreurs.append("adresse en double dans le fichier")
            vus.add(v.email)
        # Les valeurs refusées ne sont pas renvoyées : seul le numéro de ligne situe l'erreur.
        rapport.append({"ligne": numero, "nom": v.nom.upper() if v else None, "prenom": v.prenom if v else None,
                        "email": v.email if v else None, "erreurs": erreurs})
        if not erreurs:
            valides.append(v)
    resultat = {"lignes": len(rapport), "valides": len(valides), "invalides": len(rapport) - len(valides),
                "rapport": rapport, "importes": 0}
    if not donnees.confirmer or resultat["invalides"]:
        return resultat
    for v in valides:
        creer_etudiant(session, request, principal, v, classe)
        resultat["importes"] += 1
    tracer(session, request, "ETUDIANTS_IMPORTES", "SUCCES", acteur=principal, ressource="etudiant",
           details={"nombre": resultat["importes"], "classe": classe.code if classe else None})
    session.commit()
    return resultat


# --- Routes internes utilisées par le service Notes (saisie groupée, délibération) ---

@interne_classes.get("/{classe_id}")
def interne_classe(classe_id: uuid.UUID, session: Session = Depends(db)):
    c = _classe(session, classe_id)
    membres = session.scalars(select(Etudiant).where(Etudiant.classe_id == c.id)
                              .order_by(Etudiant.nom, Etudiant.prenom)).all()
    return {**_vue_classe(c, len(membres)), "etudiants": [_resume(e) for e in membres]}


@interne_classes.get("")
def interne_classes_lister(annee: str = Query(pattern=r"^\d{4}-\d{4}$"), session: Session = Depends(db)):
    effectifs = _effectifs(session)
    return [_vue_classe(c, effectifs.get(c.id, 0))
            for c in session.scalars(select(Classe).where(Classe.annee_academique == annee).order_by(Classe.code))]
