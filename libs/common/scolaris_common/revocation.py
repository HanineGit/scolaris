"""Révocation immédiate des sessions (US06, US07, US11 ; risques R02, R06, R07).

Un jeton d'accès JWT est vérifié localement par chaque service : sans
mécanisme supplémentaire, il resterait valable jusqu'à 15 minutes après la
désactivation d'un compte. Le service Authentification diffuse donc chaque
révocation sur le bus (échange « fanout ») ; chaque service la garde en
mémoire pendant la durée de vie maximale d'un jeton et refuse tout jeton émis
avant elle. Une resynchronisation périodique auprès du service
Authentification couvre une éventuelle indisponibilité du bus.
"""
import json
import logging
import ssl
import threading
import time

from .config import SECRETS_DIR, lire_secret

log = logging.getLogger("revocation")

ECHANGE = "scolaris.revocations"
# Route du service Authentification lue par les autres services (contrat vérifié par les tests d'auth).
CHEMIN_RESYNCHRONISATION = "/internal/comptes/revocations"
DUREE_CONSERVATION_S = 16 * 60  # durée de vie d'un jeton d'accès + marge


def maintenant_ms() -> int:
    return int(time.time() * 1000)


class Registre:
    def __init__(self):
        self._revocations: dict[str, int] = {}
        self._verrou = threading.Lock()

    def ajouter(self, utilisateur_id: str, instant_ms: int) -> None:
        with self._verrou:
            if instant_ms > self._revocations.get(utilisateur_id, 0):
                self._revocations[utilisateur_id] = instant_ms
            self._purger()

    def est_revoque(self, utilisateur_id: str, emis_ms: int) -> bool:
        with self._verrou:
            instant = self._revocations.get(utilisateur_id)
        return instant is not None and emis_ms <= instant

    def _purger(self) -> None:
        limite = maintenant_ms() - DUREE_CONSERVATION_S * 1000
        for cle in [k for k, v in self._revocations.items() if v < limite]:
            del self._revocations[cle]


def parametres_amqp(url: str):
    """Paramètres de connexion RabbitMQ ; en amqps, le certificat du serveur est vérifié avec l'AC interne."""
    import pika

    parametres = pika.URLParameters(url)
    if url.startswith("amqps://"):
        contexte = ssl.create_default_context(cafile=str(SECRETS_DIR / "ca_cert"))
        contexte.minimum_version = ssl.TLSVersion.TLSv1_2
        parametres.ssl_options = pika.SSLOptions(contexte, parametres.host)
    return parametres


def publier(url: str, utilisateur_id: str, instant_ms: int) -> None:
    import pika

    connexion = pika.BlockingConnection(parametres_amqp(url))
    try:
        canal = connexion.channel()
        canal.exchange_declare(exchange=ECHANGE, exchange_type="fanout", durable=True)
        canal.basic_publish(exchange=ECHANGE, routing_key="",
                            body=json.dumps({"utilisateur_id": utilisateur_id, "instant_ms": instant_ms}).encode())
    finally:
        connexion.close()


class Abonne(threading.Thread):
    """Écoute les révocations et resynchronise périodiquement le registre."""

    def __init__(self, registre: Registre, url: str, synchroniser=None, intervalle_sync: float = 30.0):
        super().__init__(daemon=True, name="revocations")
        self.registre, self.url = registre, url
        self.synchroniser, self.intervalle_sync = synchroniser, intervalle_sync
        self._arret = threading.Event()
        self._derniere_sync = 0.0

    def _sync(self):
        if self.synchroniser and time.time() - self._derniere_sync >= self.intervalle_sync:
            self._derniere_sync = time.time()
            try:
                for uid, instant in self.synchroniser():
                    self.registre.ajouter(uid, instant)
            except Exception:
                log.warning("Resynchronisation des révocations impossible ; nouvel essai plus tard.")

    def run(self):
        import pika

        while not self._arret.is_set():
            self._sync()
            try:
                connexion = pika.BlockingConnection(parametres_amqp(self.url))
                canal = connexion.channel()
                canal.exchange_declare(exchange=ECHANGE, exchange_type="fanout", durable=True)
                file = canal.queue_declare(queue="", exclusive=True).method.queue
                canal.queue_bind(exchange=ECHANGE, queue=file)
                for methode, _, corps in canal.consume(file, auto_ack=True, inactivity_timeout=1):
                    if self._arret.is_set():
                        break
                    self._sync()
                    if methode is None:
                        continue
                    try:
                        msg = json.loads(corps)
                        self.registre.ajouter(str(msg["utilisateur_id"]), int(msg["instant_ms"]))
                    except (ValueError, KeyError, TypeError):
                        log.error("Message de révocation mal formé ignoré.")
                connexion.close()
            except Exception:
                log.warning("Bus indisponible pour les révocations ; nouvel essai dans 5 s.")
                self._arret.wait(5)

    def arreter(self):
        self._arret.set()


def synchroniseur_http(base_url: str, nom_secret: str):
    """Fonction de resynchronisation : interroge CHEMIN_RESYNCHRONISATION du service Authentification."""
    import httpx

    def lire():
        r = httpx.get(f"{base_url.rstrip('/')}{CHEMIN_RESYNCHRONISATION}",
                      headers={"X-Service-Token": lire_secret(nom_secret)}, timeout=5)
        r.raise_for_status()
        return [(e["utilisateur_id"], int(e["instant_ms"])) for e in r.json()]

    return lire
