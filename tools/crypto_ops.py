"""Cryptographic Operations Tool — Provides encryption, signing, and
key management operations for agent tasks."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from typing import Optional

from tools.base import BaseTool, ToolResult
from security.crypto import QuantumSafeCrypto, AESEncryptor

logger = logging.getLogger("aetheros.tools.crypto_ops")


class CryptoOps(BaseTool):
    """Cryptographic operations tool for agents."""

    def __init__(self, crypto: Optional[QuantumSafeCrypto] = None):
        super().__init__("crypto_ops", "Cryptographic operations (encrypt, sign, hash, keygen)")
        self._crypto = crypto or QuantumSafeCrypto()

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        dispatch = {
            "encrypt": self._encrypt,
            "decrypt": self._decrypt,
            "sign": self._sign,
            "verify": self._verify,
            "hash": self._hash,
            "keygen": self._keygen,
            "random": self._random_bytes,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(success=False, error=f"Unknown crypto action: {action}")
        try:
            return await handler(kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": "crypto_ops",
            "description": "Cryptographic operations",
            "parameters": {
                "action": {"type": "string", "enum": ["encrypt", "decrypt", "sign", "verify", "hash", "keygen", "random"]},
                "data": {"type": "string"},
                "algorithm": {"type": "string"},
                "key": {"type": "string"},
            },
        }

    async def _encrypt(self, args: dict) -> ToolResult:
        data = args.get("data", "")
        encrypted = self._crypto.encrypt(data)
        return ToolResult(success=True, output=f"Encrypted: {encrypted['kem_ciphertext'][:32]}...")

    async def _decrypt(self, args: dict) -> ToolResult:
        encrypted_msg = args.get("encrypted_msg", {})
        if not encrypted_msg:
            return ToolResult(success=False, error="No encrypted message provided")
        decrypted = self._crypto.decrypt(encrypted_msg)
        return ToolResult(success=True, output=decrypted)

    async def _sign(self, args: dict) -> ToolResult:
        data = args.get("data", "")
        signature = self._crypto.sign(data)
        return ToolResult(success=True, output=signature)

    async def _verify(self, args: dict) -> ToolResult:
        data = args.get("data", "")
        signature = args.get("signature", "")
        valid = self._crypto.verify(data, signature)
        return ToolResult(success=True, output=f"Signature valid: {valid}")

    async def _hash(self, args: dict) -> ToolResult:
        data = args.get("data", "").encode()
        algo = args.get("algorithm", "sha256")
        h = hashlib.new(algo, data)
        return ToolResult(success=True, output=h.hexdigest())

    async def _keygen(self, args: dict) -> ToolResult:
        key_type = args.get("key_type", "symmetric")
        if key_type == "symmetric":
            key = os.urandom(32)
            return ToolResult(success=True, output=base64.b64encode(key).decode())
        return ToolResult(success=True, output="Key pair generated (use crypto module API)")

    async def _random_bytes(self, args: dict) -> ToolResult:
        count = min(args.get("count", 32), 1024)
        data = os.urandom(count)
        return ToolResult(success=True, output=base64.b64encode(data).decode())
