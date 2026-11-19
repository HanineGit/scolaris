"""Publication des événements d'audit (F12) par boîte d'envoi transactionnelle.

L'événement est d'abord écrit dans la base du service, dans la même
transaction que l'opération métier. Un relais l'envoie ensuite au bus
RabbitMQ et ne le marque comme envoyé qu'après confirmation du broker.
Ainsi, une indisponibilité du bus ou du service d'audit ne fait perdre
aucun événement (risque R25) et ne bloque pas l'opération métier.
"""
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Uuid, select
from sqlalchemy.orm import Mapped, mapped_column

from .logs import id_correlation, masquer
from .types import HorodatageUTC

log = logging.getLogger("audit")

FILE_AUDIT = "scolaris.audit"
# Les notifications passent par la même boîte d'envoi mais par une file distincte :
# le service d'audit ne les reçoit pas, le service de notifications ne voit pas le journal.
FILE_NOTIFICATIONS = "scolaris.notifications"
CATEGORIES_NOTIFICATION = ("NOTES", "RECLAMATION", "SECURITE", "COMPTE")


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def modele_boite_envoi(Base):
    """Crée la table de boîte d'envoi dans les métadonnées du service."""

    class EvenementSortant(Base):
        __tablename__ = "evenement_sortant"
        id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
        cree_le: Mapped[datetime] = mapped_column(HorodatageUTC, default=maintenant, index=True)
        contenu: Mapped[dict] = mapped_column(JSON)
        envoye: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    return EvenementSortant


def construire_evenement(
    *, service: str, action: str, resultat: str, acteur_id=None, acteur_identifiant: str | None = None,
    role: str | None = None, ressource: str | None = None, ressource_id=None, adresse_ip: str | None = None,
    details: dict | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "horodatage": maintenant().isoformat(),
        "service": service,
        "action": action,
        "resultat": resultat,
        "acteur_id": str(acteur_id) if acteur_id else None,
        "acteur_identifiant": acteur_identifiant,
        "role": role,
        "ressource": ressource,
        "ressource_id": str(ressource_id) if ressource_id else None,
        "adresse_ip": adresse_ip,
        "id_correlation": id_correlation.get(),
        # Aucun mot de passe, jeton ni secret ne quitte le service (risque R24).
        "details": masquer(details or {}),
    }


def enregistrer(session, Modele, evenement: dict) -> None:
    """Ajoute l'événement à la transaction en cours (commit par l'appelant)."""
    session.add(Modele(contenu=evenement))


def notifier(session, Modele, *, categorie: str, titre: str, message: str, utilisateurs=(), etudiants=(),
             lien: str | None = None) -> None:
    """Prévient des utilisateurs (par compte ou par fiche étudiant) dans la transaction en cours.

    Le texte ne contient jamais de valeur de note ni de donnée sensible : il invite
    seulement à consulter l'application, où les droits sont de nouveau vérifiés.
    """
    if categorie not in CATEGORIES_NOTIFICATION:
        raise ValueError(categorie)
    destinataires = [{"utilisateur_id": str(u)} for u in utilisateurs] + [{"etudiant_id": str(e)} for e in etudiants]
    if not destinataires:
        return
    session.add(Modele(contenu={
        "genre": "notification", "id": str(uuid.uuid4()), "horodatage": maintenant().isoformat(),
        "categorie": categorie, "titre": titre[:120], "message": message[:300], "lien": lien,
        "destinataires": destinataires,
    }))


class PublieurRabbit:
    def __init__(self, url: str):
        self.url = url
        self._connexion = None
        self._canal = None

    def _canal_ouvert(self):
        import pika

        if self._connexion is None or self._connexion.is_closed:
            from .revocation import parametres_amqp

            self._connexion = pika.BlockingConnection(parametres_amqp(self.url))
            self._canal = self._connexion.channel()
            self._canal.queue_declare(queue=FILE_AUDIT, durable=True)
            self._canal.queue_declare(queue=FILE_NOTIFICATIONS, durable=True)
            self._canal.confirm_delivery()
        return self._canal

    def publier(self, evenement: dict) -> None:
        import pika

        self._canal_ouvert().basic_publish(
            exchange="",
            routing_key=FILE_NOTIFICATIONS if evenement.get("genre") == "notification" else FILE_AUDIT,
            body=json.dumps(evenement, ensure_ascii=False).encode(),
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
            mandatory=True,
        )


class PublieurMemoire:
    """Utilisé dans les tests."""

    def __init__(self):
        self.evenements: list[dict] = []

    def publier(self, evenement: dict) -> None:
        self.evenements.append(evenement)


def relayer_une_fois(fabrique_session, Modele, publieur, lot: int = 100) -> int:
    envoyes = 0
    with fabrique_session() as session:
        while envoyes < lot:
            # Verrou par ligne : quand le service tourne sur plusieurs processus,
            # chaque événement est réservé par un seul d'entre eux.
            ev = session.scalars(
                select(Modele).where(Modele.envoye.is_(False)).order_by(Modele.cree_le)
                .limit(1).with_for_update(skip_locked=True)
            ).first()
            if ev is None:
                break
            publieur.publier(ev.contenu)
            ev.envoye = True
            session.commit()
            envoyes += 1
    return envoyes


class Relais(threading.Thread):
    """Thread qui vide périodiquement la boîte d'envoi vers le bus."""

    def __init__(self, fabrique_session, Modele, publieur, intervalle: float = 2.0):
        super().__init__(daemon=True, name="relais-audit")
        self.args_ = (fabrique_session, Modele, publieur)
        self.intervalle = intervalle
        self._arret = threading.Event()

    def run(self):
        while not self._arret.is_set():
            try:
                relayer_une_fois(*self.args_)
            except Exception:
                log.warning("Bus d'événements indisponible ; nouvel essai plus tard.")
            self._arret.wait(self.intervalle)

    def arreter(self):
        self._arret.set()


def adresse_ip(request) -> str | None:
    if request is None:
        return None
    # La passerelle Nginx transmet l'adresse réelle dans X-Real-IP.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


class Traceur:
    """Enregistre un événement d'audit dans la boîte d'envoi du service.

    « acteur » peut être un Principal (jeton) ou tout objet ayant id, identifiant et role.
    """

    def __init__(self, service: str, Modele):
        self.service = service
        self.Modele = Modele

    def __call__(self, session, request, action, resultat, *, acteur=None, role=None,
                 ressource=None, ressource_id=None, details=None):
        acteur_id = getattr(acteur, "id", acteur)
        identifiant = getattr(acteur, "identifiant", None)
        role = role or getattr(acteur, "role", None)
        enregistrer(session, self.Modele, construire_evenement(
            service=self.service, action=action, resultat=resultat, acteur_id=acteur_id,
            acteur_identifiant=identifiant, role=role, ressource=ressource, ressource_id=ressource_id,
            adresse_ip=adresse_ip(request), details=details,
        ))
