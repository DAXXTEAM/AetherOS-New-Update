"""AetherOS Utils — Hashing Utilities."""
import hashlib
import hmac
import os
from typing import Union


class HashUtils:
    """Common hashing operations."""

    @staticmethod
    def sha256(data: Union[str, bytes]) -> str:
        if isinstance(data, str):
            data = data.encode()
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def sha512(data: Union[str, bytes]) -> str:
        if isinstance(data, str):
            data = data.encode()
        return hashlib.sha512(data).hexdigest()

    @staticmethod
    def md5(data: Union[str, bytes]) -> str:
        if isinstance(data, str):
            data = data.encode()
        return hashlib.md5(data).hexdigest()

    @staticmethod
    def hmac_sha256(key: str, message: str) -> str:
        return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def file_hash(filepath: str, algorithm: str = "sha256") -> str:
        h = hashlib.new(algorithm)
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def random_token(length: int = 32) -> str:
        return os.urandom(length).hex()
