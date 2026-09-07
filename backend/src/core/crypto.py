import os

from cryptography.fernet import Fernet, InvalidToken


_PREFIX = "enc:"


def _fernet() -> Fernet | None:
    key = os.getenv("DATA_ENCRYPTION_KEY")
    return Fernet(key.encode("utf-8")) if key else None


def encrypt_text(value: str) -> str:
    fernet = _fernet()
    if not fernet or value.startswith(_PREFIX):
        return value
    return _PREFIX + fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value
    fernet = _fernet()
    if not fernet:
        raise RuntimeError("DATA_ENCRYPTION_KEY is required to decrypt persisted data")
    try:
        return fernet.decrypt(value[len(_PREFIX):].encode("utf-8")).decode("utf-8")
    except InvalidToken as error:
        raise RuntimeError("DATA_ENCRYPTION_KEY cannot decrypt persisted data") from error


def encryption_enabled() -> bool:
    return _fernet() is not None
