"""Chaînage des événements par empreinte SHA-256 et vérification d'intégrité.

empreinte(n) = SHA-256( empreinte(n-1) || contenu canonique de l'événement n )

Modifier, supprimer ou insérer un événement au milieu du journal rompt la
chaîne à partir de cet endroit : la vérification le détecte.
"""
import hashlib
import json
import logging
import threading
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from scolaris_common.logs import masquer

from .models import EvenementAudit, VerificationIntegrite

log = logging.getLogger("audit.chaine")
ORIGINE = "0" * 64
CHAMPS = ("id", "horodatage", "service", "action", "resultat", "acteur_id", "acteur_identifiant", "role",
          "ressource", "ressource_id", "adresse_ip", "id_correlation", "details")


class EvenementRecu(BaseModel):
    """Contrôle de forme des messages reçus du bus : tout message mal formé est écarté."""
    model_config = ConfigDict(extra="ignore")
    id: uuid.UUID
    horodatage: datetime
    service: str = Field(max_length=20)
    action: str = Field(pattern=r"^[A-Z_]{3,40}$")
    resultat: str = Field(pattern=r"^(SUCCES|ECHEC|REFUSE|ALERTE)$")
    acteur_id: uuid.UUID | None = None
    acteur_identifiant: str | None = Field(default=None, max_length=80)
    role: str | None = Field(default=None, max_length=20)
    ressource: str | None = Field(default=None, max_length=120)
    ressource_id: str | None = Field(default=None, max_length=64)
    adresse_ip: str | None = Field(default=None, max_length=45)
    id_correlation: str | None = Field(default=None, max_length=36)
    details: dict = Field(default_factory=dict)


def canonique(e: EvenementAudit) -> bytes:
    contenu = {
        "id": str(e.id), "horodatage": e.horodatage.isoformat(), "service": e.service, "action": e.action,
        "resultat": e.resultat, "acteur_id": str(e.acteur_id) if e.acteur_id else None,
        "acteur_identifiant": e.acteur_identifiant, "role": e.role, "ressource": e.ressource,
        "ressource_id": e.ressource_id, "adresse_ip": e.adresse_ip, "id_correlation": e.id_correlation,
        "details": e.details,
    }
    return json.dumps(contenu, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def calculer(precedente: str, e: EvenementAudit) -> str:
    return hashlib.sha256(precedente.encode() + canonique(e)).hexdigest()


def inserer(fabrique, brut: dict) -> bool:
    """Ajoute un événement en fin de chaîne. Retourne False s'il était déjà présent (idempotence)."""
    ev = EvenementRecu.model_validate(brut)
    for _ in range(3):
        with fabrique() as s:
            if s.bind.dialect.name == "postgresql":
                # Un seul écrivain à la fois en fin de chaîne.
                s.execute(text("SELECT pg_advisory_xact_lock(424242)"))
            if s.scalar(select(EvenementAudit.numero).where(EvenementAudit.id == ev.id)) is not None:
                return False
            dernier = s.scalar(select(EvenementAudit).order_by(EvenementAudit.numero.desc()).limit(1))
            e = EvenementAudit(
                numero=(dernier.numero + 1) if dernier else 1, id=ev.id, horodatage=ev.horodatage,
                service=ev.service, action=ev.action, resultat=ev.resultat, acteur_id=ev.acteur_id,
                acteur_identifiant=ev.acteur_identifiant, role=ev.role, ressource=ev.ressource,
                ressource_id=ev.ressource_id, adresse_ip=ev.adresse_ip, id_correlation=ev.id_correlation,
                details=masquer(ev.details),  # seconde barrière contre les secrets (R24)
                empreinte_precedente=dernier.empreinte if dernier else ORIGINE,
            )
            e.empreinte = calculer(e.empreinte_precedente, e)
            s.add(e)
            try:
                s.commit()
                return True
            except IntegrityError:
                s.rollback()
    raise RuntimeError("Impossible d'ajouter l'événement en fin de chaîne.")


def verifier(fabrique) -> VerificationIntegrite:
    """Recalcule toute la chaîne et enregistre le résultat (sans rien modifier au journal)."""
    precedente, nombre, defaut = ORIGINE, 0, None
    with fabrique() as s:
        for e in s.scalars(select(EvenementAudit).order_by(EvenementAudit.numero)).yield_per(500):
            nombre += 1
            if e.numero != nombre or e.empreinte_precedente != precedente or calculer(precedente, e) != e.empreinte:
                defaut = e.numero
                break
            precedente = e.empreinte
        resultat = VerificationIntegrite(integre=defaut is None, nombre=nombre, premier_defaut=defaut)
        s.add(resultat)
        s.commit()
    if defaut is not None:
        log.critical("Rupture de la chaîne d'audit détectée à l'événement n° %s.", defaut)
    return resultat


class Consommateur(threading.Thread):
    """Lit la file RabbitMQ et accuse réception seulement après écriture en base."""

    def __init__(self, fabrique, url: str):
        super().__init__(daemon=True, name="consommateur-audit")
        self.fabrique, self.url = fabrique, url
        self._arret = threading.Event()

    def run(self):
        import pika

        from scolaris_common.audit import FILE_AUDIT

        while not self._arret.is_set():
            try:
                from scolaris_common.revocation import parametres_amqp

                connexion = pika.BlockingConnection(parametres_amqp(self.url))
                canal = connexion.channel()
                canal.queue_declare(queue=FILE_AUDIT, durable=True)
                canal.basic_qos(prefetch_count=1)
                for methode, _, corps in canal.consume(FILE_AUDIT, inactivity_timeout=1):
                    if self._arret.is_set():
                        break
                    if methode is None:
                        continue
                    try:
                        inserer(self.fabrique, json.loads(corps))
                        canal.basic_ack(methode.delivery_tag)
                    except (ValueError, TypeError):
                        log.error("Message d'audit mal formé écarté.")
                        canal.basic_nack(methode.delivery_tag, requeue=False)
                connexion.close()
            except Exception:
                log.warning("Bus d'événements indisponible ; nouvel essai dans 5 s.")
                self._arret.wait(5)

    def arreter(self):
        self._arret.set()


class VerificateurQuotidien(threading.Thread):
    def __init__(self, fabrique, intervalle: float = 24 * 3600):
        super().__init__(daemon=True, name="verification-audit")
        self.fabrique, self.intervalle = fabrique, intervalle
        self._arret = threading.Event()

    def run(self):
        while not self._arret.is_set():
            try:
                verifier(self.fabrique)
            except Exception:
                log.exception("Échec de la vérification d'intégrité.")
            self._arret.wait(self.intervalle)

    def arreter(self):
        self._arret.set()
