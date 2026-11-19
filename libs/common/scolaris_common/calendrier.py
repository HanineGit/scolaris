"""Calendrier universitaire commun aux services."""
import re
from datetime import date

ANNEE_RE = re.compile(r"^(\d{4})-(\d{4})$")


def annee_academique(jour: date | None = None) -> str:
    """L'année académique commence en septembre : « 2026-2027 »."""
    jour = jour or date.today()
    debut = jour.year if jour.month >= 9 else jour.year - 1
    return f"{debut}-{debut + 1}"


def annee_valide(valeur: str) -> str:
    m = ANNEE_RE.fullmatch(valeur)
    if not m or int(m.group(2)) != int(m.group(1)) + 1:
        raise ValueError("année académique au format AAAA-AAAA (années consécutives)")
    return valeur
