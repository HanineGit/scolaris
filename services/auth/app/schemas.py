"""Schémas de validation des entrées (liste blanche, champs inconnus refusés)."""
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

NOM_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' \-]{1,59}$")
TEXTE_JETON = Field(min_length=20, max_length=128, pattern=r"^[A-Za-z0-9_\-\.]+$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Connexion(Strict):
    identifiant: str = Field(min_length=3, max_length=254)
    mot_de_passe: str = Field(min_length=1, max_length=128)


class VerificationMfa(Strict):
    jeton_mfa: str = Field(min_length=20, max_length=2048)
    code: str = Field(pattern=r"^\d{6}$")


class Rafraichissement(Strict):
    jeton_rafraichissement: str = Field(min_length=20, max_length=128)


class VerifActivation(Strict):
    jeton: str = TEXTE_JETON


class Activation(Strict):
    jeton: str = TEXTE_JETON
    mot_de_passe: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=128)
    code_totp: str | None = Field(default=None, pattern=r"^\d{6}$")


def _nom(v: str) -> str:
    if not NOM_RE.fullmatch(v):
        raise ValueError("lettres, espaces, apostrophes et traits d'union uniquement (2 à 60 caractères)")
    return v


class CreationCompte(Strict):
    nom: str
    prenom: str
    email: EmailStr = Field(max_length=254)
    role: Literal["ENSEIGNANT", "ADMINISTRATEUR"]

    _v_nom = field_validator("nom", "prenom")(_nom)

    @field_validator("email")
    @classmethod
    def minuscules(cls, v: str) -> str:
        return v.lower()


class ModificationCompte(Strict):
    role: Literal["ENSEIGNANT", "ADMINISTRATEUR"] | None = None
    statut: Literal["ACTIF", "DESACTIVE"] | None = None


class CompteEtudiant(Strict):
    etudiant_id: UUID
    matricule: str = Field(pattern=r"^ETU-\d{4}-\d{4}$")
    email: EmailStr = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def minuscules(cls, v: str) -> str:
        return v.lower()


class EmailInterne(Strict):
    email: EmailStr = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def minuscules(cls, v: str) -> str:
        return v.lower()


class EtatsInternes(Strict):
    ids: list[UUID] = Field(max_length=50)


class StatutInterne(Strict):
    statut: Literal["ACTIF", "DESACTIVE"]


# --- Réponses ---

class UtilisateurPublic(BaseModel):
    id: UUID
    identifiant: str
    role: str
    nom: str | None = None
    prenom: str | None = None


class Jetons(BaseModel):
    jeton_acces: str
    jeton_rafraichissement: str
    expire_dans: int = 900
    utilisateur: UtilisateurPublic


class EtapeMfa(BaseModel):
    mfa_requis: bool = True
    jeton_mfa: str


class CompteVue(BaseModel):
    id: UUID
    identifiant: str
    email: str
    nom: str | None
    prenom: str | None
    role: str
    statut: str
    derniere_connexion: str | None
