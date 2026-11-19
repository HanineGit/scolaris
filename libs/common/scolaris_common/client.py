"""Client des appels entre services (réseau interne, jeton de service)."""
import logging

import httpx

from .config import lire_secret
from .errors import ErreurMetier
from .logs import id_correlation

log = logging.getLogger("client_interne")


class ClientInterne:
    def __init__(self, base_url: str, nom_secret: str, delai: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.nom_secret = nom_secret
        self.delai = delai

    def _appel(self, methode: str, chemin: str, **kwargs):
        entetes = {
            "X-Service-Token": lire_secret(self.nom_secret),
            "X-Correlation-Id": id_correlation.get() if id_correlation.get() != "-" else "",
        }
        try:
            r = httpx.request(methode, self.base_url + chemin, headers=entetes, timeout=self.delai, **kwargs)
        except httpx.HTTPError:
            log.error("Service interne injoignable : %s", self.base_url)
            raise ErreurMetier(503, "Service temporairement indisponible. Réessayez plus tard.", "INDISPONIBLE")
        if r.status_code in (404, 409):
            message = r.json().get("erreur", {}).get("message", "Conflit.")
            raise ErreurMetier(r.status_code, message, "INTROUVABLE" if r.status_code == 404 else "DOUBLON")
        if r.status_code >= 400:
            log.error("Appel interne refusé (%s) : %s %s", r.status_code, methode, chemin)
            raise ErreurMetier(503, "Service temporairement indisponible. Réessayez plus tard.", "INDISPONIBLE")
        return r.json() if r.content else None

    def get(self, chemin: str, **kw):
        return self._appel("GET", chemin, **kw)

    def post(self, chemin: str, json=None):
        return self._appel("POST", chemin, json=json)

    def patch(self, chemin: str, json=None):
        return self._appel("PATCH", chemin, json=json)
