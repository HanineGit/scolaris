"""Validation des entrées du service Étudiants (liste blanche)."""
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from scolaris_common.calendrier import annee_valide

NOM_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' \-]{1,59}$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _nom(v: str) -> str:
    if not NOM_RE.fullmatch(v):
        raise ValueError("lettres, espaces, apostrophes et traits d'union uniquement (2 à 60 caractères)")
    return v


def _email(v: str) -> str:
    return v.lower()


class CreationEtudiant(Strict):
    nom: str
    prenom: str
    email: EmailStr = Field(max_length=254)
    classe_id: UUID | None = None

    _v_nom = field_validator("nom", "prenom")(_nom)
    _v_email = field_validator("email")(_email)


class ModificationEtudiant(Strict):
    nom: str | None = None
    prenom: str | None = None
    email: EmailStr | None = Field(default=None, max_length=254)
    version: int = Field(ge=1)

    @field_validator("nom", "prenom")
    @classmethod
    def v_nom(cls, v):
        return _nom(v) if v is not None else v

    @field_validator("email")
    @classmethod
    def v_email(cls, v):
        return _email(v) if v is not None else v


class Archivage(Strict):
    confirmation_matricule: str = Field(pattern=r"^ETU-\d{4}-\d{4}$")
    version: int = Field(ge=1)


class IdsInternes(Strict):
    ids: list[UUID] = Field(max_length=100)


class EtudiantVue(BaseModel):
    id: UUID
    matricule: str
    nom: str
    prenom: str
    email: str
    statut: str
    compte: str | None = None
    classe_id: UUID | None = None
    classe: str | None = None
    cree_le: str
    version: int


# --- Classes (promotions) ---

class CreationClasse(Strict):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9\-]{1,11}$")
    libelle: str = Field(min_length=3, max_length=80, pattern=r"^[\w À-ÿ'’\-().]+$")
    filiere: str = Field(min_length=2, max_length=60, pattern=r"^[\w À-ÿ'’\-]+$")
    niveau: str = Field(pattern=r"^(L1|L2|L3|M1|M2)$")
    annee_academique: str

    @field_validator("code", mode="before")
    @classmethod
    def v_code(cls, v):
        return v.upper() if isinstance(v, str) else v

    @field_validator("annee_academique")
    @classmethod
    def v_annee(cls, v):
        return annee_valide(v)


class ModificationClasse(Strict):
    libelle: str | None = Field(default=None, min_length=3, max_length=80, pattern=r"^[\w À-ÿ'’\-().]+$")
    active: bool | None = None


class Inscription(Strict):
    classe_id: UUID | None
    version: int = Field(ge=1)
