"""Chiffrement AES-256-GCM des secrets TOTP au repos."""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scolaris_common.config import lire_secret


def _cle() -> bytes:
    cle = base64.b64decode(lire_secret("mfa_encryption_key"))
    if len(cle) != 32:
        raise RuntimeError("La clé de chiffrement MFA doit faire 256 bits.")
    return cle


def chiffrer(clair: str, contexte: bytes) -> bytes:
    """Le contexte (identifiant du compte) lie le chiffré à son propriétaire."""
    nonce = os.urandom(12)
    return nonce + AESGCM(_cle()).encrypt(nonce, clair.encode(), contexte)


def dechiffrer(chiffre: bytes, contexte: bytes) -> str:
    return AESGCM(_cle()).decrypt(chiffre[:12], chiffre[12:], contexte).decode()
