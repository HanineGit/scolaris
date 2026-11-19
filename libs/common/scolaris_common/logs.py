"""Journalisation technique au format JSON, sans donnée secrète (risque R24)."""
import json
import logging
import re
import sys
from contextvars import ContextVar

id_correlation: ContextVar[str] = ContextVar("id_correlation", default="-")

CLES_SENSIBLES = re.compile(
    r"(mot_?de_?passe|password|passwd|secret|token|jeton|authorization|code_totp|cookie)",
    re.IGNORECASE,
)
MASQUE = "***"


def masquer(valeur):
    """Masque récursivement les champs sensibles d'un dictionnaire ou d'une liste."""
    if isinstance(valeur, dict):
        return {k: (MASQUE if CLES_SENSIBLES.search(str(k)) else masquer(v)) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [masquer(v) for v in valeur]
    return valeur


class FormatJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entree = {
            "horodatage": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "niveau": record.levelname,
            "service": getattr(record, "service", record.name),
            "message": record.getMessage(),
            "id_correlation": id_correlation.get(),
        }
        extra = getattr(record, "donnees", None)
        if extra:
            entree["donnees"] = masquer(extra)
        if record.exc_info:
            # La trace complète reste côté serveur, jamais renvoyée au client.
            entree["exception"] = self.formatException(record.exc_info)
        return json.dumps(entree, ensure_ascii=False)


def configurer(service: str, niveau: str = "INFO") -> logging.Logger:
    racine = logging.getLogger()
    racine.handlers.clear()
    sortie = logging.StreamHandler(sys.stdout)
    sortie.setFormatter(FormatJson())
    racine.addHandler(sortie)
    racine.setLevel(niveau)
    # Les journaux d'accès d'uvicorn contiennent les URL : on les limite.
    logging.getLogger("uvicorn.access").setLevel("WARNING")
    return logging.getLogger(service)
