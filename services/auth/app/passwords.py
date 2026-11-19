"""Hachage Argon2id et politique de mot de passe (F02, risque R05)."""
import re
from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Paramètres retenus dans la conception : 64 Mo, 3 itérations, 4 fils.
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)

# Empreinte factice : on vérifie quand même un mot de passe si le compte
# n'existe pas, pour que le temps de réponse ne révèle rien (risque R03).
_EMPREINTE_FACTICE = _hasher.hash("compte-inexistant-valeur-factice")

LONGUEUR_MIN = 12
LONGUEUR_MAX = 128


def hacher(mot_de_passe: str) -> str:
    return _hasher.hash(mot_de_passe)


def verifier(empreinte: str | None, mot_de_passe: str) -> bool:
    try:
        return _hasher.verify(empreinte or _EMPREINTE_FACTICE, mot_de_passe) and empreinte is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def _mots_de_passe_divulgues() -> frozenset[str]:
    fichier = Path(__file__).parent / "data" / "mots_de_passe_divulgues.txt"
    lignes = fichier.read_text(encoding="utf-8").splitlines()
    return frozenset(l.strip().lower() for l in lignes if l.strip() and not l.startswith("#"))


def regles_non_respectees(mot_de_passe: str, *interdits: str) -> list[str]:
    """Retourne la liste des règles non respectées (vide si le mot de passe est conforme)."""
    erreurs = []
    if not (LONGUEUR_MIN <= len(mot_de_passe) <= LONGUEUR_MAX):
        erreurs.append(f"entre {LONGUEUR_MIN} et {LONGUEUR_MAX} caractères")
    if not re.search(r"[a-z]", mot_de_passe) or not re.search(r"[A-Z]", mot_de_passe):
        erreurs.append("une majuscule et une minuscule")
    if not re.search(r"\d", mot_de_passe):
        erreurs.append("au moins un chiffre")
    if not re.search(r"[^A-Za-z0-9]", mot_de_passe):
        erreurs.append("au moins un caractère spécial")
    bas = mot_de_passe.lower()
    if bas in _mots_de_passe_divulgues():
        erreurs.append("absent des listes de mots de passe divulgués")
    for valeur in interdits:
        if valeur and len(valeur) >= 4 and valeur.lower().split("@")[0] in bas:
            erreurs.append("ne pas contenir votre identifiant ou votre adresse e-mail")
            break
    return erreurs
