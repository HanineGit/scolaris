"""Validation des entrées du service Notes."""
import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scolaris_common.calendrier import annee_valide

TypeEvaluation = Literal["CONTROLE_CONTINU", "EXAMEN", "TP", "RATTRAPAGE"]
Valeur = Field(ge=0, le=20, max_digits=4, decimal_places=2)
LIBELLE_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9' ,\-()]{1,79}$")
MOTIF_INTERDIT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f<>]")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _libelle(v: str) -> str:
    if not LIBELLE_RE.fullmatch(v):
        raise ValueError("2 à 80 caractères : lettres, chiffres, espaces et ponctuation simple")
    return v


class CreationMatiere(Strict):
    code: str = Field(pattern=r"^[A-Z0-9]{2,10}$")
    libelle: str
    coefficient: Decimal = Field(ge=Decimal("0.5"), le=10, max_digits=3, decimal_places=1)
    classe_id: UUID | None = None
    semestre_id: UUID | None = None

    _v = field_validator("libelle")(_libelle)


class ModificationMatiere(Strict):
    libelle: str | None = None
    coefficient: Decimal | None = Field(default=None, ge=Decimal("0.5"), le=10, max_digits=3, decimal_places=1)
    active: bool | None = None
    classe_id: UUID | None = None
    semestre_id: UUID | None = None

    @field_validator("libelle")
    @classmethod
    def v_libelle(cls, v):
        return _libelle(v) if v is not None else v


class NouvelleAffectation(Strict):
    enseignant_id: UUID


class NouvelleNote(Strict):
    matiere_id: UUID
    etudiant_id: UUID
    type_evaluation: TypeEvaluation
    date_evaluation: date
    valeur: Decimal = Valeur

    @field_validator("date_evaluation")
    @classmethod
    def pas_dans_le_futur(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("la date d'évaluation ne peut pas être dans le futur")
        return v


class ModificationNote(Strict):
    valeur: Decimal = Valeur
    motif: str = Field(min_length=10, max_length=255)
    version: int = Field(ge=1)

    @field_validator("motif")
    @classmethod
    def motif_propre(cls, v: str) -> str:
        if MOTIF_INTERDIT.search(v):
            raise ValueError("caractères de contrôle et chevrons interdits")
        return v


def _texte_propre(v: str) -> str:
    if MOTIF_INTERDIT.search(v):
        raise ValueError("caractères de contrôle et chevrons interdits")
    return v


# --- F17 Calendrier et fenêtres de saisie ---

class CreationSemestre(Strict):
    annee_academique: str
    numero: Literal[1, 2]
    saisie_debut: date | None = None
    saisie_fin: date | None = None

    _v_annee = field_validator("annee_academique")(annee_valide)

    @model_validator(mode="after")
    def fenetre(self):
        if (self.saisie_debut is None) != (self.saisie_fin is None):
            raise ValueError("indiquer le début et la fin de la fenêtre de saisie")
        if self.saisie_debut and self.saisie_fin < self.saisie_debut:
            raise ValueError("la fin de la fenêtre précède son début")
        return self


class FenetreSaisie(Strict):
    saisie_debut: date
    saisie_fin: date

    @model_validator(mode="after")
    def ordre(self):
        if self.saisie_fin < self.saisie_debut:
            raise ValueError("la fin de la fenêtre précède son début")
        return self


# --- F18 Publication ---

class Depublication(Strict):
    motif: str = Field(min_length=10, max_length=255)

    _v = field_validator("motif")(_texte_propre)


# --- F21 Saisie groupée ---

class LigneSaisie(Strict):
    etudiant_id: UUID
    valeur: Decimal = Valeur


class SaisieGroupee(Strict):
    type_evaluation: TypeEvaluation
    date_evaluation: date
    notes: list[LigneSaisie] = Field(min_length=1, max_length=300)

    @field_validator("date_evaluation")
    @classmethod
    def pas_dans_le_futur(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("la date d'évaluation ne peut pas être dans le futur")
        return v

    @model_validator(mode="after")
    def sans_doublon(self):
        ids = [l.etudiant_id for l in self.notes]
        if len(ids) != len(set(ids)):
            raise ValueError("un étudiant figure deux fois dans la saisie")
        return self


# --- F19 Réclamations ---

class NouvelleReclamation(Strict):
    note_id: UUID
    motif: str = Field(min_length=20, max_length=500)

    _v = field_validator("motif")(_texte_propre)


class TraitementReclamation(Strict):
    decision: Literal["EN_COURS", "ACCEPTEE", "REJETEE"]
    reponse: str = Field(min_length=10, max_length=500)
    nouvelle_valeur: Decimal | None = Field(default=None, ge=0, le=20, max_digits=4, decimal_places=2)
    version: int = Field(ge=1)

    _v = field_validator("reponse")(_texte_propre)

    @model_validator(mode="after")
    def valeur_si_acceptee(self):
        if self.decision == "ACCEPTEE" and self.nouvelle_valeur is None:
            raise ValueError("une réclamation acceptée indique la nouvelle note")
        if self.decision != "ACCEPTEE" and self.nouvelle_valeur is not None:
            raise ValueError("seule une réclamation acceptée modifie la note")
        return self
