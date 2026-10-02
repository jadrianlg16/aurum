"""Encrypted e.firma vault: cer/key bytes + CIEC-style password, encrypted at rest with a passphrase.

Key derivation: scrypt(passphrase, salt) -> Fernet key. The passphrase itself, the derived key, and the
decrypted cer/key material are never written to disk or logs — only the encrypted blob and a random salt
are persisted. `status()` reports metadata only (never material). Read-only: nothing here signs or
transmits SAT filings; it exists to feed `client.py`'s Descarga Masiva requests.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from ..core.config import settings

_SALT_LEN = 16


class VaultError(Exception):
    pass


class VaultNotFound(VaultError):
    pass


class VaultBadPassphrase(VaultError):
    pass


@dataclass
class VaultCredentials:
    cer_bytes: bytes
    key_bytes: bytes
    password: str


def _vault_path(ws_id: str) -> Path:
    return settings().vault_dir / f"{ws_id}.vault"


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def store(ws_id: str, cer_bytes: bytes, key_bytes: bytes, password: str, passphrase: str) -> dict:
    """Encrypt and persist e.firma material. Returns status metadata only (no material)."""
    salt = os.urandom(_SALT_LEN)
    fkey = _derive_key(passphrase, salt)
    payload = json.dumps(
        {
            "cer_b64": base64.b64encode(cer_bytes).decode("ascii"),
            "key_b64": base64.b64encode(key_bytes).decode("ascii"),
            "password": password,
        }
    ).encode("utf-8")
    token = Fernet(fkey).encrypt(payload)

    path = _vault_path(ws_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(salt + b"\n" + token)
    return status(ws_id)


def status(ws_id: str) -> dict:
    path = _vault_path(ws_id)
    if not path.exists():
        return {"present": False}
    stat = path.stat()
    return {
        "present": True,
        "stored_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(timespec="seconds"),
        "size_bytes": stat.st_size,
    }


def open_vault(ws_id: str, passphrase: str) -> VaultCredentials:
    """Decrypt and return credentials in memory only. Never logs or persists the passphrase/material."""
    path = _vault_path(ws_id)
    if not path.exists():
        raise VaultNotFound(ws_id)
    raw = path.read_bytes()
    # The salt is random bytes and may itself contain 0x0A, so never split on the newline separator:
    # read it by its fixed length and skip the one-byte separator that follows it.
    salt, token = raw[:_SALT_LEN], raw[_SALT_LEN + 1 :]
    fkey = _derive_key(passphrase, salt)
    try:
        payload = Fernet(fkey).decrypt(token)
    except InvalidToken as e:
        raise VaultBadPassphrase("incorrect passphrase") from e
    data = json.loads(payload.decode("utf-8"))
    return VaultCredentials(
        cer_bytes=base64.b64decode(data["cer_b64"]),
        key_bytes=base64.b64decode(data["key_b64"]),
        password=data["password"],
    )


def purge(ws_id: str) -> bool:
    path = _vault_path(ws_id)
    if path.exists():
        path.unlink()
        return True
    return False
