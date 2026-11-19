"""F04 Ajout, F05 Consultation, F06 Modification et archivage des étudiants."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from scolaris_common import audit
from scolaris_common.errors import ErreurMetier
from scolaris_common.security import ADMINISTRATEUR, Principal, exiger_roles, exiger_service

from .models import Classe, Etudiant, EvenementSortant
from .schemas import Archivage, CreationEtudiant, EtudiantVue, IdsInternes, ModificationEtudiant

router = APIRouter(prefix="/api/v1/etudiants", tags=["étudiants"])
interne = APIRouter(prefix="/internal/etudiants", include_in_schema=False,
                    dependencies=[Depends(exiger_service("service_token_notes"))])
admin = exiger_roles(ADMINISTRATEUR)
tracer = audit.Traceur("etudiants", EvenementSortant)


def db(request: Request):
    yield from request.app.state.bdd.session()


def _vue(e: Etudiant, compte: str | None = None) -> EtudiantVue:
    return EtudiantVue(id=e.id, matricule=e.matricule, nom=e.nom, prenom=e.prenom, email=e.email,
                       statut=e.statut, compte=compte, classe_id=e.classe_id,
                       classe=e.classe.code if e.classe else None, cree_le=e.cree_le.isoformat(), version=e.version)


def classe_ouverte(session: Session, classe_id: uuid.UUID | None) -> Classe | None:
    """Une inscription n'est possible que dans une classe existante et active."""
    if classe_id is None:
        return None
    c = session.get(Classe, classe_id)
    if c is None or not c.active:
        raise ErreurMetier(422, "Classe introuvable ou fermée.", "CLASSE")
    return c


def _charger(session: Session, etudiant_id: uuid.UUID) -> Etudiant:
    e = session.get(Etudiant, etudiant_id)
    if e is None:
        raise ErreurMetier(404, "Étudiant introuvable.", "INTROUVABLE")
    return e


def _prochain_matricule(session: Session) -> str:
    """Matricule généré par le serveur, jamais saisi (risque R09)."""
    annee = datetime.now(timezone.utc).year
    prefixe = f"ETU-{annee}-"
    dernier = session.scalar(select(func.max(Etudiant.matricule)).where(Etudiant.matricule.like(prefixe + "%")))
    numero = int(dernier[-4:]) + 1 if dernier else 1
    return f"{prefixe}{numero:04d}"


@router.post("", response_model=EtudiantVue, status_code=201)
def ajouter(donnees: CreationEtudiant, request: Request, principal: Principal = Depends(admin),
            session: Session = Depends(db)):
    e = creer_etudiant(session, request, principal, donnees, classe_ouverte(session, donnees.classe_id))
    return _vue(e, "EN_ATTENTE_ACTIVATION")


def creer_etudiant(session: Session, request: Request, principal: Principal, donnees: CreationEtudiant,
                   classe: Classe | None) -> Etudiant:
    """Ajout unitaire ou par import : mêmes contrôles, même compte, même trace d'audit."""
    e = Etudiant(matricule=_prochain_matricule(session), nom=donnees.nom.upper(), prenom=donnees.prenom,
                 email=donnees.email, classe=classe, cree_par=principal.id)
    session.add(e)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Un étudiant utilise déjà cette adresse e-mail.", "DOUBLON")
    # Le compte est créé dans le service Authentification, qui envoie le lien d'activation (F02).
    try:
        compte = request.app.state.auth.post("/internal/comptes/etudiants", json={
            "etudiant_id": str(e.id), "matricule": e.matricule, "email": e.email})
    except ErreurMetier:
        session.rollback()
        raise
    e.utilisateur_id = uuid.UUID(compte["utilisateur_id"])
    tracer(session, request, "ETUDIANT_AJOUTE", "SUCCES", acteur=principal, ressource="etudiant",
           ressource_id=e.id, details={"matricule": e.matricule, "classe": classe.code if classe else None})
    session.commit()
    return e


@router.get("", response_model=dict)
def lister(
    request: Request,
    q: str | None = Query(default=None, max_length=60),
    statut: str = Query(default="ACTIF", pattern="^(ACTIF|ARCHIVE)$"),
    page: int = Query(default=1, ge=1, le=10_000),
    taille: int = Query(default=20, ge=1, le=50),  # pas d'extraction massive (R11)
    classe_id: uuid.UUID | None = None,
    principal: Principal = Depends(admin), session: Session = Depends(db),
):
    requete = select(Etudiant).where(Etudiant.statut == statut)
    if classe_id:
        requete = requete.where(Etudiant.classe_id == classe_id)
    if q:
        motif = f"%{q.lower()}%"
        requete = requete.where(or_(func.lower(Etudiant.nom).like(motif), func.lower(Etudiant.prenom).like(motif),
                                    func.lower(Etudiant.matricule).like(motif)))
    total = session.scalar(select(func.count()).select_from(requete.subquery()))
    etudiants = session.scalars(requete.order_by(Etudiant.nom, Etudiant.prenom)
                                .offset((page - 1) * taille).limit(taille)).all()
    etats = {}
    ids = [str(e.utilisateur_id) for e in etudiants if e.utilisateur_id]
    if ids:
        try:
            etats = request.app.state.auth.post("/internal/comptes/etats", json={"ids": ids})
        except ErreurMetier:
            etats = {}  # l'état du compte est une information secondaire : la liste reste disponible
    compteurs = dict(session.execute(select(Etudiant.statut, func.count()).group_by(Etudiant.statut)).all())
    return {
        "total": total, "page": page, "actifs": compteurs.get("ACTIF", 0), "archives": compteurs.get("ARCHIVE", 0),
        "elements": [_vue(e, etats.get(str(e.utilisateur_id))).model_dump(mode="json") for e in etudiants],
    }


@router.get("/{etudiant_id}", response_model=EtudiantVue)
def fiche(etudiant_id: uuid.UUID, request: Request, principal: Principal = Depends(admin),
          session: Session = Depends(db)):
    e = _charger(session, etudiant_id)
    compte = None
    if e.utilisateur_id:
        try:
            compte = (request.app.state.auth.get(f"/internal/comptes/{e.utilisateur_id}") or {}).get("statut")
        except ErreurMetier:
            compte = None
    return _vue(e, compte)


@router.patch("/{etudiant_id}", response_model=EtudiantVue)
def modifier(etudiant_id: uuid.UUID, donnees: ModificationEtudiant, request: Request,
             principal: Principal = Depends(admin), session: Session = Depends(db)):
    e = _charger(session, etudiant_id)
    if e.statut == "ARCHIVE":
        raise ErreurMetier(409, "Un étudiant archivé ne peut plus être modifié.", "ARCHIVE")
    if donnees.version != e.version:
        raise ErreurMetier(409, "La fiche a été modifiée entre-temps. Rechargez-la.", "VERSION")
    avant, apres = {}, {}
    for champ in ("nom", "prenom", "email"):
        valeur = getattr(donnees, champ)
        if champ == "nom" and valeur:
            valeur = valeur.upper()
        if valeur is not None and valeur != getattr(e, champ):
            avant[champ], apres[champ] = getattr(e, champ), valeur
            setattr(e, champ, valeur)
    if not apres:
        return _vue(e)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ErreurMetier(409, "Un étudiant utilise déjà cette adresse e-mail.", "DOUBLON")
    except StaleDataError:
        session.rollback()
        raise ErreurMetier(409, "La fiche a été modifiée entre-temps. Rechargez-la.", "VERSION")
    if "email" in apres and e.utilisateur_id:
        try:
            request.app.state.auth.patch(f"/internal/comptes/{e.utilisateur_id}/email", json={"email": e.email})
        except ErreurMetier:
            session.rollback()
            raise
    tracer(session, request, "ETUDIANT_MODIFIE", "SUCCES", acteur=principal, ressource="etudiant",
           ressource_id=e.id, details={"avant": avant, "apres": apres})
    session.commit()
    return _vue(e)


@router.post("/{etudiant_id}/archivage", response_model=EtudiantVue)
def archiver(etudiant_id: uuid.UUID, donnees: Archivage, request: Request,
             principal: Principal = Depends(admin), session: Session = Depends(db)):
    """Archivage logique : aucune suppression physique n'existe (réponse « Éviter », R13)."""
    e = _charger(session, etudiant_id)
    if e.statut == "ARCHIVE":
        raise ErreurMetier(409, "Cet étudiant est déjà archivé.", "ARCHIVE")
    if donnees.confirmation_matricule != e.matricule:
        raise ErreurMetier(422, "Le matricule saisi ne correspond pas à cet étudiant.", "CONFIRMATION")
    if donnees.version != e.version:
        raise ErreurMetier(409, "La fiche a été modifiée entre-temps. Rechargez-la.", "VERSION")
    e.statut = "ARCHIVE"
    session.flush()
    if e.utilisateur_id:
        try:
            request.app.state.auth.patch(f"/internal/comptes/{e.utilisateur_id}/statut", json={"statut": "DESACTIVE"})
        except ErreurMetier:
            session.rollback()
            raise
    tracer(session, request, "ETUDIANT_ARCHIVE", "SUCCES", acteur=principal, ressource="etudiant",
           ressource_id=e.id, details={"matricule": e.matricule})
    session.commit()
    return _vue(e, "DESACTIVE")


# --- Routes internes, utilisées par le service Notes ---

def _resume(e: Etudiant) -> dict:
    return {"id": str(e.id), "matricule": e.matricule, "nom": e.nom, "prenom": e.prenom, "statut": e.statut}


@interne.get("/{etudiant_id}")
def interne_lire(etudiant_id: uuid.UUID, session: Session = Depends(db)):
    return _resume(_charger(session, etudiant_id))


@interne.get("")
def interne_par_matricule(matricule: str = Query(pattern=r"^ETU-\d{4}-\d{4}$"), session: Session = Depends(db)):
    e = session.scalar(select(Etudiant).where(Etudiant.matricule == matricule))
    if e is None:
        raise ErreurMetier(404, "Aucun étudiant ne porte ce matricule.", "INTROUVABLE")
    return _resume(e)


@interne.post("/lot")
def interne_lot(donnees: IdsInternes, session: Session = Depends(db)):
    etudiants = session.scalars(select(Etudiant).where(Etudiant.id.in_(donnees.ids))).all()
    return {str(e.id): _resume(e) for e in etudiants}
