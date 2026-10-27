"""Zero-Knowledge Client-Side AES-256-GCM Vault Backup:
Provides envelope encryption for .omni project bundles using PBKDF2 (600,000 iterations)
and authenticated AES-256-GCM ciphers with cryptographically random nonces.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VAULT_MAGIC_HEADER = b"OMNI_VAULT_1"  # 12 bytes
SALT_SIZE = 16                          # 16 bytes
NONCE_SIZE = 12                         # 12 bytes
PBKDF2_ITERATIONS = 600_000             # Standard OWASP recommended ceiling for SHA-256


class VaultSync:
    """Zero-knowledge AES-256-GCM project backup and restoration engine."""

    @staticmethod
    def _derive_key(password: str, salt: bytes) -> bytes:
        """Derive 256-bit AES key from master password using PBKDF2-HMAC-SHA256."""
        if not password:
            raise ValueError("Master passphrase cannot be empty.")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return kdf.derive(password.encode("utf-8"))

    @classmethod
    def encrypt_bytes(cls, data: bytes, password: str) -> bytes:
        """
        Encrypt raw bytes into authenticated vault payload:
        [12-byte MAGIC] + [16-byte SALT] + [12-byte NONCE] + [CIPHERTEXT + 16-byte TAG]
        """
        salt = os.urandom(SALT_SIZE)
        key = cls._derive_key(password, salt)
        nonce = os.urandom(NONCE_SIZE)

        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)

        return VAULT_MAGIC_HEADER + salt + nonce + ciphertext

    @classmethod
    def decrypt_bytes(cls, vault_bytes: bytes, password: str) -> bytes:
        """
        Decrypt authenticated vault payload.
        Raises InvalidTag if passphrase is incorrect or data has been altered.
        """
        header_len = len(VAULT_MAGIC_HEADER)
        if len(vault_bytes) < header_len + SALT_SIZE + NONCE_SIZE + 16:
            raise ValueError("Invalid vault file: payload is too short.")

        header = vault_bytes[:header_len]
        if header != VAULT_MAGIC_HEADER:
            raise ValueError("Invalid vault format: magic header mismatch.")

        salt_start = header_len
        salt_end = salt_start + SALT_SIZE
        salt = vault_bytes[salt_start:salt_end]

        nonce_start = salt_end
        nonce_end = nonce_start + NONCE_SIZE
        nonce = vault_bytes[nonce_start:nonce_end]

        ciphertext = vault_bytes[nonce_end:]

        key = cls._derive_key(password, salt)
        aesgcm = AESGCM(key)

        # decrypt will raise InvalidTag on authentication mismatch
        return aesgcm.decrypt(nonce, ciphertext, None)

    @classmethod
    def encrypt_file(
        cls,
        src_path: Union[str, Path],
        dest_path: Union[str, Path],
        password: str,
    ) -> Path:
        """Encrypt source file (.omni) into destination encrypted vault file (.omni.vault)."""
        src = Path(src_path)
        dest = Path(dest_path)
        if not src.exists():
            raise FileNotFoundError(f"Source project file not found: {src}")

        raw_bytes = src.read_bytes()
        vault_bytes = cls.encrypt_bytes(raw_bytes, password)

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(vault_bytes)
        return dest

    @classmethod
    def decrypt_file(
        cls,
        vault_path: Union[str, Path],
        dest_path: Union[str, Path],
        password: str,
    ) -> Path:
        """Decrypt vault file (.omni.vault) back into destination project file (.omni)."""
        vault = Path(vault_path)
        dest = Path(dest_path)
        if not vault.exists():
            raise FileNotFoundError(f"Vault file not found: {vault}")

        vault_bytes = vault.read_bytes()
        decrypted_bytes = cls.decrypt_bytes(vault_bytes, password)

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(decrypted_bytes)
        return dest
