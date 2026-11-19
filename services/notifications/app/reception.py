"""Réception des notifications publiées sur le bus par les autres services (file scolaris.notifications)."""
import json
import logging
import threading
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from scolaris_common.audit import FILE_NOTIFICATIONS

from .models import Notification

log = logging.getLogger("notifications")
# Chemin interne uniquement (« /notes », « /enseignant/reclamations ») : ni URL externe ni « // »
# (lien relatif au protocole, interprété comme un autre site par le navigateur), contre l'hameçonnage.
LIEN = r"^/(?:[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-]+)*)?$"


class Destinataire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    utilisateur_id: uuid.UUID | None = None
    etudiant_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def un_seul(self):
        if (self.utilisateur_id is None) == (self.etudiant_id is None):
            raise ValueError("un destinataire est un compte ou une fiche étudiant")
        return self


class MessageEntrant(BaseModel):
    """Liste blanche stricte : tout champ inattendu fait écarter le message."""
    model_config = ConfigDict(extra="forbid")
    genre: Literal["notification"]
    id: uuid.UUID
    horodatage: str = Field(max_length=40)
    categorie: Literal["NOTES", "RECLAMATION", "SECURITE", "COMPTE"]
    titre: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=300)
    lien: str | None = Field(default=None, max_length=120, pattern=LIEN)
    destinataires: list[Destinataire] = Field(min_length=1, max_length=2000)


def enregistrer(fabrique, brut: dict) -> int:
    """Idempotent : un message redélivré par le bus n'est enregistré qu'une fois."""
    try:
        m = MessageEntrant.model_validate(brut)
    except ValidationError as e:
        raise ValueError("message de notification invalide") from e
    with fabrique() as s:
        if s.scalar(select(Notification.id).where(Notification.message_id == m.id).limit(1)):
            return 0
        for d in m.destinataires:
            s.add(Notification(message_id=m.id, utilisateur_id=d.utilisateur_id, etudiant_id=d.etudiant_id,
                               categorie=m.categorie, titre=m.titre, message=m.message, lien=m.lien))
        s.commit()
    return len(m.destinataires)


class Consommateur(threading.Thread):
    """Lit la file et n'accuse réception qu'après écriture en base."""

    def __init__(self, fabrique, url: str):
        super().__init__(daemon=True, name="consommateur-notifications")
        self.fabrique, self.url = fabrique, url
        self._arret = threading.Event()

    def run(self):
        import pika

        from scolaris_common.revocation import parametres_amqp

        while not self._arret.is_set():
            try:
                connexion = pika.BlockingConnection(parametres_amqp(self.url))
                canal = connexion.channel()
                canal.queue_declare(queue=FILE_NOTIFICATIONS, durable=True)
                canal.basic_qos(prefetch_count=10)
                for methode, _, corps in canal.consume(FILE_NOTIFICATIONS, inactivity_timeout=1):
                    if self._arret.is_set():
                        break
                    if methode is None:
                        continue
                    try:
                        enregistrer(self.fabrique, json.loads(corps))
                        canal.basic_ack(methode.delivery_tag)
                    except (ValueError, TypeError):
                        log.error("Notification mal formée écartée.")
                        canal.basic_nack(methode.delivery_tag, requeue=False)
                connexion.close()
            except Exception:
                log.warning("Bus indisponible ; nouvel essai dans 5 s.")
                self._arret.wait(5)

    def arreter(self):
        self._arret.set()
