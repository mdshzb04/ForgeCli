"""Secure storage for API keys with OS keychain (keyring) and encrypted fallback."""

from __future__ import annotations

import base64
import contextlib
import getpass
import hashlib
import json
import sys
import uuid
from pathlib import Path

import keyring
from cryptography.fernet import Fernet

from forgecli.utils.paths import ProjectPaths

KEYRING_SERVICE = "forgecli"


def _get_credentials_file() -> Path:
    paths = ProjectPaths.from_env()
    return paths.config_dir / "credentials.json"


def _get_encryption_key() -> bytes:
    try:
        # Combine node, username, and platform as a unique host identifier
        host_info = f"{uuid.getnode()}:{getpass.getuser()}:{sys.platform}"
    except Exception:
        host_info = "fallback-forgecli-key-salt"
    key_hash = hashlib.sha256(host_info.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(key_hash)


def _read_encrypted_file() -> dict[str, str]:
    path = _get_credentials_file()
    if not path.exists():
        return {}
    try:
        raw_data = path.read_bytes()
        fernet = Fernet(_get_encryption_key())
        decrypted = fernet.decrypt(raw_data)
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        return {}


def _write_encrypted_file(data: dict[str, str]) -> None:
    path = _get_credentials_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.dumps(data).encode("utf-8")
        fernet = Fernet(_get_encryption_key())
        encrypted = fernet.encrypt(payload)
        path.write_bytes(encrypted)
    except Exception:
        pass


def set_api_key(provider: str, api_key: str) -> bool:
    """Store the API key for a provider.

    Returns True if stored in keyring, False if stored in fallback file.
    """
    provider = provider.lower().strip()
    # Try keyring first
    try:
        # Verify the keyring is actually working and not a dummy keyring
        # Some headless linux environments return a dummy keyring that silently ignores set_password or throws errors
        keyring.set_password(KEYRING_SERVICE, provider, api_key)
        # Test retrieval to make sure it actually saved
        retrieved = keyring.get_password(KEYRING_SERVICE, provider)
        if retrieved == api_key:
            return True
    except Exception:
        pass

    # Fallback to encrypted file
    data = _read_encrypted_file()
    data[provider] = api_key
    _write_encrypted_file(data)
    return False


def get_api_key(provider: str) -> str | None:
    """Retrieve the API key for a provider."""
    provider = provider.lower().strip()
    # Try keyring first
    try:
        val = keyring.get_password(KEYRING_SERVICE, provider)
        if val is not None:
            return val
    except Exception:
        pass
    # Try fallback
    data = _read_encrypted_file()
    return data.get(provider)


def delete_api_key(provider: str) -> None:
    """Delete the API key for a provider."""
    provider = provider.lower().strip()
    with contextlib.suppress(Exception):
        keyring.delete_password(KEYRING_SERVICE, provider)
    data = _read_encrypted_file()
    if provider in data:
        del data[provider]
        _write_encrypted_file(data)


def delete_all_api_keys() -> None:
    """Delete all stored keys."""
    providers = [
        "openai",
        "anthropic",
        "google",
        "openrouter",
        "groq",
        "mistral",
        "ollama",
        "lmstudio",
        "vllm",
    ]
    for p in providers:
        with contextlib.suppress(Exception):
            keyring.delete_password(KEYRING_SERVICE, p)
    path = _get_credentials_file()
    if path.exists():
        with contextlib.suppress(Exception):
            path.unlink()


def list_authenticated_providers() -> list[str]:
    """Get a list of providers with saved API keys."""
    providers = [
        "openai",
        "anthropic",
        "google",
        "openrouter",
        "groq",
        "mistral",
        "ollama",
        "lmstudio",
        "vllm",
    ]
    auth_list = []
    for p in providers:
        if get_api_key(p):
            auth_list.append(p)
    return auth_list
