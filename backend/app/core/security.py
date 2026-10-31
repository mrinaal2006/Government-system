"""Security primitives: password hashing, tokens, field encryption, TOTP.

* Passwords: Argon2id (argon2-cffi), parameters above OWASP minimums.
* Session/CSRF tokens: 256-bit random; only their SHA-256 is stored server-side.
* Field encryption: Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from
  DATA_ENCRYPTION_KEY; previous keys can still decrypt (rotation via MultiFernet).
* Lookup hashes: HMAC-SHA256 with LOOKUP_HMAC_KEY so encrypted values (e.g. mobile
  numbers) can be matched for duplicate detection without decrypting them.
* TOTP: RFC 6238 via pyotp, 30 s step, +/-1 step tolerance, replay-protected by the caller.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import Environment, get_settings

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2, hash_len=32, salt_len=16)

# A small deny-list of passwords that satisfy length rules but are trivially guessable.
_COMMON = {
    "password1234",
    "passwordpassword",
    "qwertyuiop12",
    "123456789012",
    "administrator",
    "welcome@1234",
    "india@123456",
    "admin@123456",
}


class WeakPasswordError(ValueError):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# Used to equalise timing when the username does not exist.
DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(16))


def validate_password_policy(password: str, *, username: str, full_name: str = "") -> None:
    settings = get_settings()
    problems = []
    if len(password) < settings.password_min_length:
        problems.append(f"must be at least {settings.password_min_length} characters")
    if len(password) > 256:
        problems.append("must be at most 256 characters")
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        problems.append("must use at least three of: lower case, upper case, digits, symbols")
    lowered = password.lower()
    if username and username.lower() in lowered:
        problems.append("must not contain the username")
    for part in full_name.lower().split():
        if len(part) >= 4 and part in lowered:
            problems.append("must not contain your name")
            break
    if lowered in _COMMON:
        problems.append("is too common")
    if problems:
        raise WeakPasswordError("Password " + "; ".join(problems) + ".")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(("dgimews-fernet:" + secret).encode()).digest())


@lru_cache(maxsize=1)
def _cipher() -> MultiFernet:
    settings = get_settings()
    primary = settings.data_encryption_key.get_secret_value()
    if not primary:
        if settings.app_env in (Environment.DEVELOPMENT, Environment.TEST):
            raise RuntimeError("DATA_ENCRYPTION_KEY is not set (run scripts/init-dev-env.sh)")
        raise RuntimeError("DATA_ENCRYPTION_KEY is required")
    keys = [primary, *settings.data_encryption_previous_keys]
    return MultiFernet([Fernet(_fernet_key(k)) for k in keys])


def encrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _cipher().encrypt(value.encode()).decode()


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Encrypted value could not be decrypted with configured keys") from exc


def lookup_hash(value: str | None) -> str | None:
    if not value:
        return None
    key = get_settings().lookup_hmac_key.get_secret_value()
    if not key:
        raise RuntimeError("LOOKUP_HMAC_KEY is required")
    normalised = "".join(value.split()).lower()
    return hmac.new(key.encode(), normalised.encode(), hashlib.sha256).hexdigest()


def reset_crypto_caches() -> None:
    _cipher.cache_clear()


# --- TOTP -------------------------------------------------------------------------------


def new_totp_secret() -> str:
    return pyotp.random_base32(length=32)


def totp_provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=get_settings().mfa_issuer)


def totp_matching_step(secret: str, code: str, *, at: float | None = None) -> int | None:
    """Return the time step the code is valid for (+/-1 step), or None."""
    if not code.isdigit() or len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    import time

    now = at if at is not None else time.time()
    for offset in (0, -1, 1):
        t = now + offset * totp.interval
        if hmac.compare_digest(totp.at(int(t)), code):
            return int(t // totp.interval)
    return None


def mask(value: str | None, keep: int = 2) -> str | None:
    if value is None:
        return None
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]
