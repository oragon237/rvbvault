from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import struct
from ctypes import wintypes
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"RVB1"
PASSWORD_BACKUP_MAGIC = b"RVB2PBK1"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))), buf


def dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        return data
    in_blob, keepalive = _blob(data)
    out_blob = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), "RVB Vault key", None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        return data
    in_blob, keepalive = _blob(data)
    out_blob = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


class LocalCipher:
    """AES-GCM cipher whose key is protected by the current Windows user account."""

    def __init__(self, key_file: Path) -> None:
        self.key_file = key_file
        self._key = self._load_or_create_key()

    def _load_or_create_key(self) -> bytes:
        if self.key_file.exists():
            return dpapi_unprotect(self.key_file.read_bytes())
        key = AESGCM.generate_key(bit_length=256)
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self.key_file.write_bytes(dpapi_protect(key))
        try:
            self.key_file.chmod(0o600)
        except OSError:
            pass
        return key

    def encrypt(self, plaintext: str | bytes, *, context: bytes = b"field") -> bytes:
        data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
        nonce = os.urandom(12)
        return MAGIC + nonce + AESGCM(self._key).encrypt(nonce, data, context)

    def decrypt(self, payload: bytes, *, context: bytes = b"field") -> bytes:
        if not payload.startswith(MAGIC) or len(payload) < 17:
            raise ValueError("Invalid encrypted payload")
        nonce = payload[4:16]
        return AESGCM(self._key).decrypt(nonce, payload[16:], context)


def encrypt_with_password(plaintext: bytes, password: str) -> bytes:
    """Create a portable authenticated payload without persisting the derived key."""
    if len(password) < 10:
        raise ValueError("Recovery password must be at least 10 characters")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))
    encrypted = AESGCM(key).encrypt(nonce, plaintext, PASSWORD_BACKUP_MAGIC)
    return PASSWORD_BACKUP_MAGIC + salt + nonce + encrypted


def decrypt_with_password(payload: bytes, password: str) -> bytes:
    if not payload.startswith(PASSWORD_BACKUP_MAGIC) or len(payload) < 52:
        raise ValueError("Not a password-protected RVB backup")
    salt = payload[8:24]
    nonce = payload[24:36]
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))
    try:
        return AESGCM(key).decrypt(nonce, payload[36:], PASSWORD_BACKUP_MAGIC)
    except Exception as exc:
        raise ValueError("Incorrect recovery password or damaged backup") from exc


def create_password_verifier(password: str) -> bytes:
    salt = os.urandom(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return struct.pack(">I", iterations) + salt + digest


def verify_password(password: str, verifier: bytes) -> bool:
    if len(verifier) != 52:
        return False
    iterations = struct.unpack(">I", verifier[:4])[0]
    salt, expected = verifier[4:20], verifier[20:]
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
