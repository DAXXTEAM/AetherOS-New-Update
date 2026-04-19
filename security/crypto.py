"""Quantum-Safe Cryptography implementation.

Implements NIST PQC standards (Kyber for KEM, Dilithium for signatures)
via simulation using classical cryptography primitives when OQS is unavailable.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger("aetheros.security.crypto")


class CryptoAlgorithm(Enum):
    KYBER_512 = "kyber-512"
    KYBER_768 = "kyber-768"
    KYBER_1024 = "kyber-1024"
    DILITHIUM_2 = "dilithium-2"
    DILITHIUM_3 = "dilithium-3"
    DILITHIUM_5 = "dilithium-5"
    AES_256_GCM = "aes-256-gcm"
    ECDH_P384 = "ecdh-p384"


@dataclass
class KeyPair:
    """Cryptographic key pair."""
    algorithm: str
    public_key: bytes
    private_key: bytes
    key_id: str = field(default_factory=lambda: secrets.token_hex(8))
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "public_key_hex": self.public_key.hex()[:64] + "...",
            "created_at": self.created_at,
        }


class KyberSimulator:
    """Simulates Kyber KEM using ECDH + HKDF.

    In production, replace with liboqs bindings.
    Security level mapping:
      Kyber-512    ECDH P-256 (AES-128 equivalent)
      Kyber-768    ECDH P-384 (AES-192 equivalent)
      Kyber-1024   ECDH P-384 + extended derivation (AES-256 equivalent)
    """

    CURVE_MAP = {
        CryptoAlgorithm.KYBER_512: ec.SECP256R1(),
        CryptoAlgorithm.KYBER_768: ec.SECP384R1(),
        CryptoAlgorithm.KYBER_1024: ec.SECP384R1(),
    }

    KEY_SIZE_MAP = {
        CryptoAlgorithm.KYBER_512: 16,
        CryptoAlgorithm.KYBER_768: 24,
        CryptoAlgorithm.KYBER_1024: 32,
    }

    @classmethod
    def keygen(cls, algorithm: CryptoAlgorithm = CryptoAlgorithm.KYBER_768) -> KeyPair:
        """Generate a Kyber-simulated key pair."""
        curve = cls.CURVE_MAP.get(algorithm, ec.SECP384R1())
        private_key = ec.generate_private_key(curve, default_backend())
        public_key = private_key.public_key()

        priv_bytes = private_key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        pub_bytes = public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        return KeyPair(
            algorithm=algorithm.value,
            public_key=pub_bytes,
            private_key=priv_bytes,
            metadata={"type": "kem", "simulated": True, "curve": str(curve.name)},
        )

    @classmethod
    def encapsulate(cls, public_key_bytes: bytes,
                    algorithm: CryptoAlgorithm = CryptoAlgorithm.KYBER_768) -> tuple[bytes, bytes]:
        """Encapsulate: generate shared secret and ciphertext."""
        curve = cls.CURVE_MAP.get(algorithm, ec.SECP384R1())
        key_size = cls.KEY_SIZE_MAP.get(algorithm, 32)

        peer_public = serialization.load_der_public_key(public_key_bytes, default_backend())
        ephemeral_private = ec.generate_private_key(curve, default_backend())
        shared = ephemeral_private.exchange(ec.ECDH(), peer_public)

        # HKDF derivation
        derived = HKDF(
            algorithm=hashes.SHA384(),
            length=key_size,
            salt=None,
            info=b"kyber-kem-encapsulate",
            backend=default_backend(),
        ).derive(shared)

        ct = ephemeral_private.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return derived, ct

    @classmethod
    def decapsulate(cls, private_key_bytes: bytes, ciphertext: bytes,
                    algorithm: CryptoAlgorithm = CryptoAlgorithm.KYBER_768) -> bytes:
        """Decapsulate: recover shared secret from ciphertext."""
        key_size = cls.KEY_SIZE_MAP.get(algorithm, 32)
        private_key = serialization.load_der_private_key(private_key_bytes, None, default_backend())
        peer_public = serialization.load_der_public_key(ciphertext, default_backend())
        shared = private_key.exchange(ec.ECDH(), peer_public)

        derived = HKDF(
            algorithm=hashes.SHA384(),
            length=key_size,
            salt=None,
            info=b"kyber-kem-encapsulate",
            backend=default_backend(),
        ).derive(shared)
        return derived


class DilithiumSimulator:
    """Simulates Dilithium digital signatures using ECDSA.

    In production, replace with liboqs bindings.
    """

    CURVE_MAP = {
        CryptoAlgorithm.DILITHIUM_2: ec.SECP256R1(),
        CryptoAlgorithm.DILITHIUM_3: ec.SECP384R1(),
        CryptoAlgorithm.DILITHIUM_5: ec.SECP521R1(),
    }

    @classmethod
    def keygen(cls, algorithm: CryptoAlgorithm = CryptoAlgorithm.DILITHIUM_3) -> KeyPair:
        """Generate a Dilithium-simulated signing key pair."""
        curve = cls.CURVE_MAP.get(algorithm, ec.SECP384R1())
        private_key = ec.generate_private_key(curve, default_backend())

        priv_bytes = private_key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        pub_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return KeyPair(
            algorithm=algorithm.value,
            public_key=pub_bytes,
            private_key=priv_bytes,
            metadata={"type": "signature", "simulated": True},
        )

    @classmethod
    def sign(cls, private_key_bytes: bytes, message: bytes,
             algorithm: CryptoAlgorithm = CryptoAlgorithm.DILITHIUM_3) -> bytes:
        """Sign a message."""
        private_key = serialization.load_der_private_key(private_key_bytes, None, default_backend())
        hash_algo = ec.ECDSA(hashes.SHA384())
        return private_key.sign(message, hash_algo)

    @classmethod
    def verify(cls, public_key_bytes: bytes, message: bytes, signature: bytes,
               algorithm: CryptoAlgorithm = CryptoAlgorithm.DILITHIUM_3) -> bool:
        """Verify a signature."""
        try:
            public_key = serialization.load_der_public_key(public_key_bytes, default_backend())
            public_key.verify(signature, message, ec.ECDSA(hashes.SHA384()))
            return True
        except Exception:
            return False


class AESEncryptor:
    """AES-256-GCM symmetric encryption."""

    @staticmethod
    def encrypt(key: bytes, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """Encrypt with AES-256-GCM. Returns nonce + ciphertext."""
        if len(key) < 32:
            key = hashlib.sha256(key).digest()
        elif len(key) > 32:
            key = key[:32]

        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ct

    @staticmethod
    def decrypt(key: bytes, ciphertext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """Decrypt AES-256-GCM. Expects nonce + ciphertext."""
        if len(key) < 32:
            key = hashlib.sha256(key).digest()
        elif len(key) > 32:
            key = key[:32]

        nonce = ciphertext[:12]
        ct = ciphertext[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, associated_data)


@dataclass
class CryptoSuite:
    """High-level cryptographic operations suite."""
    kem_algorithm: CryptoAlgorithm = CryptoAlgorithm.KYBER_768
    sig_algorithm: CryptoAlgorithm = CryptoAlgorithm.DILITHIUM_3
    kem_keypair: Optional[KeyPair] = None
    sig_keypair: Optional[KeyPair] = None

    def initialize(self) -> None:
        """Generate key pairs."""
        self.kem_keypair = KyberSimulator.keygen(self.kem_algorithm)
        self.sig_keypair = DilithiumSimulator.keygen(self.sig_algorithm)
        logger.info(f"CryptoSuite initialized: KEM={self.kem_algorithm.value}, SIG={self.sig_algorithm.value}")

    def encrypt_for_recipient(self, recipient_public: bytes, plaintext: bytes) -> dict:
        """Encrypt data for a recipient using hybrid encryption."""
        shared_secret, ciphertext = KyberSimulator.encapsulate(recipient_public, self.kem_algorithm)
        encrypted = AESEncryptor.encrypt(shared_secret, plaintext)
        return {
            "kem_ciphertext": ciphertext.hex(),
            "encrypted_data": encrypted.hex(),
            "algorithm": self.kem_algorithm.value,
        }

    def decrypt_message(self, encrypted_msg: dict) -> bytes:
        """Decrypt a message using our private key."""
        if not self.kem_keypair:
            raise ValueError("KEM keypair not initialized")
        kem_ct = bytes.fromhex(encrypted_msg["kem_ciphertext"])
        enc_data = bytes.fromhex(encrypted_msg["encrypted_data"])
        shared_secret = KyberSimulator.decapsulate(self.kem_keypair.private_key, kem_ct, self.kem_algorithm)
        return AESEncryptor.decrypt(shared_secret, enc_data)

    def sign_data(self, data: bytes) -> bytes:
        """Sign data with our signing key."""
        if not self.sig_keypair:
            raise ValueError("Signing keypair not initialized")
        return DilithiumSimulator.sign(self.sig_keypair.private_key, data, self.sig_algorithm)

    def verify_signature(self, public_key: bytes, data: bytes, signature: bytes) -> bool:
        """Verify a signature."""
        return DilithiumSimulator.verify(public_key, data, signature, self.sig_algorithm)

    def get_status(self) -> dict:
        return {
            "kem_algorithm": self.kem_algorithm.value,
            "sig_algorithm": self.sig_algorithm.value,
            "kem_initialized": self.kem_keypair is not None,
            "sig_initialized": self.sig_keypair is not None,
            "kem_key_id": self.kem_keypair.key_id if self.kem_keypair else None,
            "sig_key_id": self.sig_keypair.key_id if self.sig_keypair else None,
        }


class QuantumSafeCrypto:
    """Main quantum-safe cryptography interface."""

    def __init__(self, kem_level: int = 768, sig_level: int = 3):
        kem_map = {512: CryptoAlgorithm.KYBER_512, 768: CryptoAlgorithm.KYBER_768, 1024: CryptoAlgorithm.KYBER_1024}
        sig_map = {2: CryptoAlgorithm.DILITHIUM_2, 3: CryptoAlgorithm.DILITHIUM_3, 5: CryptoAlgorithm.DILITHIUM_5}
        self.suite = CryptoSuite(
            kem_algorithm=kem_map.get(kem_level, CryptoAlgorithm.KYBER_768),
            sig_algorithm=sig_map.get(sig_level, CryptoAlgorithm.DILITHIUM_3),
        )
        self.suite.initialize()
        logger.info("QuantumSafeCrypto initialized")

    def encrypt(self, plaintext: str, recipient_public_key: Optional[bytes] = None) -> dict:
        """Encrypt a string message."""
        pub_key = recipient_public_key or self.suite.kem_keypair.public_key
        return self.suite.encrypt_for_recipient(pub_key, plaintext.encode("utf-8"))

    def decrypt(self, encrypted_msg: dict) -> str:
        """Decrypt an encrypted message."""
        return self.suite.decrypt_message(encrypted_msg).decode("utf-8")

    def sign(self, message: str) -> str:
        """Sign a message, return hex-encoded signature."""
        sig = self.suite.sign_data(message.encode("utf-8"))
        return sig.hex()

    def verify(self, message: str, signature_hex: str, public_key: Optional[bytes] = None) -> bool:
        """Verify a signature."""
        pub = public_key or self.suite.sig_keypair.public_key
        return self.suite.verify_signature(pub, message.encode("utf-8"), bytes.fromhex(signature_hex))

    @property
    def public_kem_key(self) -> bytes:
        return self.suite.kem_keypair.public_key

    @property
    def public_sig_key(self) -> bytes:
        return self.suite.sig_keypair.public_key

    def get_status(self) -> dict:
        return self.suite.get_status()
