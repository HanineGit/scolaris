"""Lecture de la configuration et des secrets.

Les secrets ne sont jamais écrits dans le code ni dans les images Docker
(risque R29). En production, Docker les monte en lecture seule dans
/run/secrets/<nom>. En développement local, une variable d'environnement
<NOM>_FILE peut désigner un autre fichier.
"""
import os
from functools import lru_cache
from pathlib import Path

SECRETS_DIR = Path(os.environ.get("SCOLARIS_SECRETS_DIR", "/run/secrets"))


class SecretManquant(RuntimeError):
    pass


@lru_cache(maxsize=None)
def lire_secret(nom: str) -> str:
    """Retourne le contenu d'un secret, sans espace final."""
    chemin = os.environ.get(f"{nom.upper()}_FILE")
    fichier = Path(chemin) if chemin else SECRETS_DIR / nom
    if not fichier.is_file():
        # Le nom du secret est indiqué, jamais sa valeur.
        raise SecretManquant(f"Secret introuvable : {nom}")
    return fichier.read_text(encoding="utf-8").strip()


def parametre(nom: str, defaut: str | None = None) -> str:
    """Paramètre non secret (nom d'hôte, durée, etc.)."""
    valeur = os.environ.get(nom, defaut)
    if valeur is None:
        raise RuntimeError(f"Paramètre manquant : {nom}")
    return valeur
