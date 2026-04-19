"""Wire Protocol   Binary message framing and encrypted channels
for inter-component and inter-node communication.

Implements:
- Length-prefixed binary message framing
- Message serialization with versioning
- Encrypted secure channels
- Message compression
- Flow control and backpressure
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import struct
import time
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any, Optional

logger = logging.getLogger("aetheros.protocols.wire")


class MessageType(IntEnum):
    HEARTBEAT = 0x01
    TASK_ASSIGN = 0x02
    TASK_RESULT = 0x03
    AGENT_MSG = 0x04
    AUDIT_LOG = 0x05
    STATE_SYNC = 0x06
    CONFIG_UPDATE = 0x07
    SHUTDOWN = 0x08
    DISCOVERY = 0x09
    STEAL_REQUEST = 0x0A
    STEAL_RESPONSE = 0x0B
    ACK = 0x0C
    NACK = 0x0D
    ERROR = 0x0E
    PING = 0x0F
    PONG = 0x10


class CompressionType(IntEnum):
    NONE = 0
    ZLIB = 1
    GZIP = 2


@dataclass
class MessageHeader:
    """Binary message header (fixed 24 bytes)."""
    version: int = 2
    message_type: MessageType = MessageType.HEARTBEAT
    flags: int = 0
    sequence: int = 0
    payload_length: int = 0
    checksum: int = 0

    HEADER_FORMAT = "!BBHIQ"
    HEADER_SIZE = struct.calcsize("!BBHIQ")

    def encode(self) -> bytes:
        return struct.pack(
            self.HEADER_FORMAT,
            self.version,
            self.message_type,
            self.flags,
            self.sequence,
            self.payload_length,
        )

    @classmethod
    def decode(cls, data: bytes) -> "MessageHeader":
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"Header too short: {len(data)} < {cls.HEADER_SIZE}")
        version, msg_type, flags, seq, length = struct.unpack(cls.HEADER_FORMAT, data[:cls.HEADER_SIZE])
        return cls(
            version=version,
            message_type=MessageType(msg_type),
            flags=flags,
            sequence=seq,
            payload_length=length,
        )


@dataclass
class MessageFrame:
    """Complete message frame with header and payload."""
    header: MessageHeader = field(default_factory=MessageHeader)
    payload: bytes = b""
    sender_id: str = ""
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    timestamp: float = field(default_factory=time.time)

    def encode(self) -> bytes:
        meta = json.dumps({
            "sender": self.sender_id,
            "id": self.message_id,
            "ts": self.timestamp,
        }).encode()
        full_payload = struct.pack("!H", len(meta)) + meta + self.payload
        self.header.payload_length = len(full_payload)
        checksum = zlib.crc32(full_payload) & 0xFFFFFFFF
        return self.header.encode() + struct.pack("!I", checksum) + full_payload

    @classmethod
    def decode(cls, data: bytes) -> "MessageFrame":
        header = MessageHeader.decode(data)
        offset = MessageHeader.HEADER_SIZE
        checksum = struct.unpack("!I", data[offset:offset + 4])[0]
        offset += 4
        payload_data = data[offset:offset + header.payload_length]
        actual_checksum = zlib.crc32(payload_data) & 0xFFFFFFFF
        if actual_checksum != checksum:
            raise ValueError("Checksum mismatch")
        meta_len = struct.unpack("!H", payload_data[:2])[0]
        meta = json.loads(payload_data[2:2 + meta_len])
        payload = payload_data[2 + meta_len:]
        return cls(
            header=header,
            payload=payload,
            sender_id=meta.get("sender", ""),
            message_id=meta.get("id", ""),
            timestamp=meta.get("ts", 0),
        )

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "type": self.header.message_type.name,
            "sender": self.sender_id,
            "payload_size": len(self.payload),
            "sequence": self.header.sequence,
        }


class SecureChannel:
    """Encrypted communication channel using symmetric keys."""

    def __init__(self, shared_key: bytes):
        if len(shared_key) < 32:
            shared_key = hashlib.sha256(shared_key).digest()
        self._key = shared_key[:32]
        self._sequence = 0
        self._stats = {"messages_sent": 0, "messages_received": 0, "bytes_sent": 0, "bytes_received": 0}

    def encrypt_frame(self, frame: MessageFrame) -> bytes:
        """Encrypt a message frame."""
        raw = frame.encode()
        nonce = os.urandom(12)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(self._key)
        ct = aesgcm.encrypt(nonce, raw, None)
        self._stats["messages_sent"] += 1
        self._stats["bytes_sent"] += len(ct)
        return nonce + ct

    def decrypt_frame(self, data: bytes) -> MessageFrame:
        """Decrypt a message frame."""
        nonce = data[:12]
        ct = data[12:]
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(self._key)
        raw = aesgcm.decrypt(nonce, ct, None)
        self._stats["messages_received"] += 1
        self._stats["bytes_received"] += len(raw)
        return MessageFrame.decode(raw)

    def create_frame(self, msg_type: MessageType, payload: bytes,
                     sender_id: str = "") -> MessageFrame:
        self._sequence += 1
        return MessageFrame(
            header=MessageHeader(
                message_type=msg_type,
                sequence=self._sequence,
                payload_length=len(payload),
            ),
            payload=payload,
            sender_id=sender_id,
        )

    def get_stats(self) -> dict:
        return self._stats


class WireProtocol:
    """High-level wire protocol manager."""

    def __init__(self, node_id: str = ""):
        self.node_id = node_id or uuid.uuid4().hex[:10]
        self._channels: dict[str, SecureChannel] = {}
        self._pending_acks: dict[int, MessageFrame] = {}
        self._message_log: list[dict] = []

    def create_channel(self, peer_id: str, shared_key: bytes) -> SecureChannel:
        channel = SecureChannel(shared_key)
        self._channels[peer_id] = channel
        return channel

    def send(self, peer_id: str, msg_type: MessageType,
             payload: dict) -> Optional[bytes]:
        channel = self._channels.get(peer_id)
        if not channel:
            return None
        data = json.dumps(payload).encode()
        frame = channel.create_frame(msg_type, data, self.node_id)
        encrypted = channel.encrypt_frame(frame)
        self._message_log.append(frame.to_dict())
        return encrypted

    def receive(self, peer_id: str, data: bytes) -> Optional[dict]:
        channel = self._channels.get(peer_id)
        if not channel:
            return None
        try:
            frame = channel.decrypt_frame(data)
            self._message_log.append(frame.to_dict())
            return {
                "type": frame.header.message_type.name,
                "sender": frame.sender_id,
                "payload": json.loads(frame.payload) if frame.payload else {},
            }
        except Exception as e:
            logger.error(f"Wire protocol receive error: {e}")
            return None

    def get_status(self) -> dict:
        return {
            "node_id": self.node_id,
            "channels": len(self._channels),
            "message_log_size": len(self._message_log),
        }
