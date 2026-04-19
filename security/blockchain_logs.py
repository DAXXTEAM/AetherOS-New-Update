"""AetherOS Security   Blockchain-Based Immutable Audit Ledger.

Implements a private blockchain for tamper-proof audit logging.
Every security event, system action, and configuration change is
recorded as a transaction in an immutable chain of blocks.

Architecture:
     
                     BlockchainAuditLedger                         
                 
         Transaction     Block             Chain                
         Pool             Builder            Validator            
                 
                                                                  
                 
         Merkle          Consensus          Persistence          
         Tree            Engine             Layer                
                 
     

Block Structure:
    Block #N
      header
          index: N
          timestamp: ISO-8601
          previous_hash: SHA-256 of block N-1
          merkle_root: root hash of transactions
          nonce: proof-of-work nonce
          difficulty: mining difficulty target
      transactions: List[AuditTransaction]
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("security.blockchain")


#  
# Enums & Constants
#  

class TransactionType(Enum):
    """Types of audit transactions."""
    SYSTEM_EVENT = "system_event"
    SECURITY_ALERT = "security_alert"
    CONFIG_CHANGE = "config_change"
    ACCESS_LOG = "access_log"
    COMMAND_EXEC = "command_exec"
    AUTH_EVENT = "auth_event"
    POLICY_CHANGE = "policy_change"
    NETWORK_EVENT = "network_event"
    EVOLUTION_EVENT = "evolution_event"
    LOCKDOWN_EVENT = "lockdown_event"
    KILL_SWITCH = "kill_switch"
    HONEYPOT_TRIGGER = "honeypot_trigger"
    OSINT_FINDING = "osint_finding"
    INTEGRITY_CHECK = "integrity_check"


class BlockStatus(Enum):
    """Block validation status."""
    VALID = "valid"
    INVALID_HASH = "invalid_hash"
    INVALID_CHAIN = "invalid_chain"
    INVALID_MERKLE = "invalid_merkle"
    TAMPERED = "tampered"
    PENDING = "pending"


GENESIS_PREV_HASH = "0" * 64
DEFAULT_DIFFICULTY = 2  # Number of leading zeros required
MAX_TRANSACTIONS_PER_BLOCK = 100
BLOCK_INTERVAL_SECONDS = 30


#  
# Data Models
#  

@dataclass
class AuditTransaction:
    """Single audit transaction in the blockchain."""
    tx_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tx_type: TransactionType = TransactionType.SYSTEM_EVENT
    actor: str = "system"
    action: str = ""
    target: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # info, warning, critical, emergency
    signature: str = ""     # HMAC signature for authenticity

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this transaction."""
        payload = json.dumps({
            "tx_id": self.tx_id,
            "timestamp": self.timestamp,
            "tx_type": self.tx_type.value,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "data": self.data,
            "severity": self.severity,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def sign(self, secret_key: str) -> None:
        """Sign the transaction with HMAC."""
        import hmac
        payload = f"{self.tx_id}:{self.timestamp}:{self.action}:{self.target}"
        self.signature = hmac.new(
            secret_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

    def verify_signature(self, secret_key: str) -> bool:
        """Verify transaction HMAC signature."""
        import hmac
        payload = f"{self.tx_id}:{self.timestamp}:{self.action}:{self.target}"
        expected = hmac.new(
            secret_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "timestamp": self.timestamp,
            "tx_type": self.tx_type.value,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "data": self.data,
            "severity": self.severity,
            "signature": self.signature,
            "hash": self.compute_hash(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditTransaction":
        return cls(
            tx_id=data.get("tx_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            tx_type=TransactionType(data.get("tx_type", "system_event")),
            actor=data.get("actor", "system"),
            action=data.get("action", ""),
            target=data.get("target", ""),
            data=data.get("data", {}),
            severity=data.get("severity", "info"),
            signature=data.get("signature", ""),
        )


#  
# Merkle Tree
#  

class MerkleTree:
    """Binary Merkle Tree for transaction integrity verification.

    Provides O(log n) proof of inclusion and tamper detection
    for transactions within a block.
    """

    def __init__(self, transactions: List[AuditTransaction]):
        self._leaves: List[str] = [tx.compute_hash() for tx in transactions]
        self._tree: List[List[str]] = []
        self._root: str = ""
        self._build_tree()

    def _build_tree(self) -> None:
        """Build the Merkle tree from leaf hashes."""
        if not self._leaves:
            self._root = hashlib.sha256(b"empty").hexdigest()
            return

        current_level = list(self._leaves)
        self._tree = [current_level]

        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256(
                    (left + right).encode()
                ).hexdigest()
                next_level.append(combined)
            self._tree.append(next_level)
            current_level = next_level

        self._root = current_level[0] if current_level else ""

    @property
    def root(self) -> str:
        return self._root

    def get_proof(self, index: int) -> List[Tuple[str, str]]:
        """Get Merkle proof for a transaction at given index.

        Returns list of (hash, direction) pairs for verification.
        """
        if index < 0 or index >= len(self._leaves):
            return []

        proof = []
        idx = index
        for level in self._tree[:-1]:
            if idx % 2 == 0:
                sibling_idx = idx + 1
                direction = "right"
            else:
                sibling_idx = idx - 1
                direction = "left"

            if sibling_idx < len(level):
                proof.append((level[sibling_idx], direction))
            idx //= 2

        return proof

    @staticmethod
    def verify_proof(tx_hash: str, proof: List[Tuple[str, str]], root: str) -> bool:
        """Verify a Merkle proof against the expected root."""
        current = tx_hash
        for sibling_hash, direction in proof:
            if direction == "left":
                combined = sibling_hash + current
            else:
                combined = current + sibling_hash
            current = hashlib.sha256(combined.encode()).hexdigest()
        return current == root

    @property
    def depth(self) -> int:
        return len(self._tree)

    @property
    def leaf_count(self) -> int:
        return len(self._leaves)


#  
# Block
#  

@dataclass
class Block:
    """A single block in the blockchain."""
    index: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    transactions: List[AuditTransaction] = field(default_factory=list)
    previous_hash: str = GENESIS_PREV_HASH
    nonce: int = 0
    difficulty: int = DEFAULT_DIFFICULTY
    merkle_root: str = ""
    block_hash: str = ""

    def __post_init__(self):
        if self.transactions and not self.merkle_root:
            tree = MerkleTree(self.transactions)
            self.merkle_root = tree.root
        if not self.block_hash:
            self.block_hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Compute the block's SHA-256 hash."""
        header = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
            "tx_count": len(self.transactions),
        }, sort_keys=True)
        return hashlib.sha256(header.encode()).hexdigest()

    def mine(self, difficulty: Optional[int] = None) -> int:
        """Mine the block (proof of work).

        Returns the nonce that produces a hash with required leading zeros.
        """
        target_prefix = "0" * (difficulty or self.difficulty)
        nonce = 0
        while True:
            self.nonce = nonce
            hash_attempt = self.compute_hash()
            if hash_attempt.startswith(target_prefix):
                self.block_hash = hash_attempt
                return nonce
            nonce += 1
            if nonce > 10_000_000:
                # Safety limit for this implementation
                self.block_hash = hash_attempt
                return nonce

    def validate(self) -> BlockStatus:
        """Validate block integrity."""
        # Check hash
        computed = self.compute_hash()
        if computed != self.block_hash:
            return BlockStatus.INVALID_HASH

        # Check difficulty
        target = "0" * self.difficulty
        if not self.block_hash.startswith(target):
            return BlockStatus.INVALID_HASH

        # Check merkle root
        if self.transactions:
            tree = MerkleTree(self.transactions)
            if tree.root != self.merkle_root:
                return BlockStatus.INVALID_MERKLE

        return BlockStatus.VALID

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "block_hash": self.block_hash,
            "merkle_root": self.merkle_root,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
            "tx_count": len(self.transactions),
            "transactions": [tx.to_dict() for tx in self.transactions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Block":
        txs = [AuditTransaction.from_dict(t) for t in data.get("transactions", [])]
        return cls(
            index=data.get("index", 0),
            timestamp=data.get("timestamp", ""),
            transactions=txs,
            previous_hash=data.get("previous_hash", GENESIS_PREV_HASH),
            nonce=data.get("nonce", 0),
            difficulty=data.get("difficulty", DEFAULT_DIFFICULTY),
            merkle_root=data.get("merkle_root", ""),
            block_hash=data.get("block_hash", ""),
        )


#  
# Blockchain Chain
#  

class BlockchainChain:
    """The blockchain itself   an ordered list of validated blocks."""

    def __init__(self, difficulty: int = DEFAULT_DIFFICULTY):
        self.difficulty = difficulty
        self._chain: List[Block] = []
        self._lock = threading.RLock()
        self._create_genesis_block()

    def _create_genesis_block(self) -> None:
        """Create the genesis (first) block."""
        genesis_tx = AuditTransaction(
            tx_id="genesis-000",
            tx_type=TransactionType.SYSTEM_EVENT,
            actor="system",
            action="genesis_block_created",
            target="blockchain",
            data={"version": "3.0", "codename": "The Singularity"},
            severity="info",
        )
        genesis = Block(
            index=0,
            transactions=[genesis_tx],
            previous_hash=GENESIS_PREV_HASH,
            difficulty=self.difficulty,
        )
        genesis.mine(difficulty=1)  # Easy mine for genesis
        self._chain.append(genesis)
        logger.info(f"Genesis block created: {genesis.block_hash[:16]}...")

    def add_block(self, transactions: List[AuditTransaction]) -> Block:
        """Create and add a new block with the given transactions."""
        with self._lock:
            prev_block = self._chain[-1]
            new_block = Block(
                index=len(self._chain),
                transactions=transactions,
                previous_hash=prev_block.block_hash,
                difficulty=self.difficulty,
            )
            new_block.mine()
            self._chain.append(new_block)
            logger.info(
                f"Block #{new_block.index} mined: {new_block.block_hash[:16]}... "
                f"({len(transactions)} txs, nonce={new_block.nonce})"
            )
            return new_block

    def validate_chain(self) -> Tuple[bool, List[str]]:
        """Validate the entire blockchain.

        Returns (is_valid, list_of_errors).
        """
        errors = []
        with self._lock:
            for i in range(len(self._chain)):
                block = self._chain[i]
                status = block.validate()
                if status != BlockStatus.VALID:
                    errors.append(f"Block #{i}: {status.value}")

                if i > 0:
                    if block.previous_hash != self._chain[i - 1].block_hash:
                        errors.append(
                            f"Block #{i}: previous_hash mismatch "
                            f"(expected {self._chain[i-1].block_hash[:16]}, "
                            f"got {block.previous_hash[:16]})"
                        )

        return (len(errors) == 0, errors)

    def get_block(self, index: int) -> Optional[Block]:
        with self._lock:
            if 0 <= index < len(self._chain):
                return self._chain[index]
            return None

    def get_latest_block(self) -> Block:
        with self._lock:
            return self._chain[-1]

    def search_transactions(
        self,
        tx_type: Optional[TransactionType] = None,
        actor: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditTransaction]:
        """Search transactions across all blocks."""
        results = []
        with self._lock:
            for block in reversed(self._chain):
                for tx in reversed(block.transactions):
                    if tx_type and tx.tx_type != tx_type:
                        continue
                    if actor and tx.actor != actor:
                        continue
                    if severity and tx.severity != severity:
                        continue
                    if since and tx.timestamp < since:
                        continue
                    results.append(tx)
                    if len(results) >= limit:
                        return results
        return results

    @property
    def length(self) -> int:
        with self._lock:
            return len(self._chain)

    @property
    def total_transactions(self) -> int:
        with self._lock:
            return sum(len(b.transactions) for b in self._chain)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "chain_length": len(self._chain),
                "difficulty": self.difficulty,
                "total_transactions": self.total_transactions,
                "blocks": [b.to_dict() for b in self._chain],
            }

    def export_json(self, filepath: str) -> bool:
        """Export the blockchain to a JSON file."""
        try:
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to export blockchain: {e}")
            return False

    def import_json(self, filepath: str) -> bool:
        """Import a blockchain from a JSON file."""
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            blocks = [Block.from_dict(b) for b in data.get("blocks", [])]
            if blocks:
                with self._lock:
                    self._chain = blocks
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to import blockchain: {e}")
            return False


#  
# Transaction Pool
#  

class TransactionPool:
    """Pool of pending transactions waiting to be included in a block."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._pool: List[AuditTransaction] = []
        self._lock = threading.Lock()
        self._processed_ids: Set[str] = set()

    def add(self, transaction: AuditTransaction) -> bool:
        """Add a transaction to the pool."""
        with self._lock:
            if transaction.tx_id in self._processed_ids:
                return False  # Duplicate
            if len(self._pool) >= self.max_size:
                # Remove oldest
                removed = self._pool.pop(0)
                self._processed_ids.discard(removed.tx_id)
            self._pool.append(transaction)
            self._processed_ids.add(transaction.tx_id)
            return True

    def drain(self, max_count: int = MAX_TRANSACTIONS_PER_BLOCK) -> List[AuditTransaction]:
        """Remove and return up to max_count transactions."""
        with self._lock:
            batch = self._pool[:max_count]
            self._pool = self._pool[max_count:]
            return batch

    def peek(self, count: int = 10) -> List[AuditTransaction]:
        with self._lock:
            return list(self._pool[:count])

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._pool)

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._pool) == 0


#  
# Consensus Engine (Single-Node Proof of Work)
#  

class ConsensusEngine:
    """Simple proof-of-work consensus for single-node operation.

    Adjusts difficulty based on block mining time to maintain
    a target block interval.
    """

    def __init__(
        self,
        target_interval: float = BLOCK_INTERVAL_SECONDS,
        min_difficulty: int = 1,
        max_difficulty: int = 6,
    ):
        self.target_interval = target_interval
        self.min_difficulty = min_difficulty
        self.max_difficulty = max_difficulty
        self._mining_times: deque = deque(maxlen=10)

    def record_mining_time(self, seconds: float) -> None:
        self._mining_times.append(seconds)

    def adjust_difficulty(self, current: int) -> int:
        """Adjust difficulty based on recent mining times."""
        if len(self._mining_times) < 3:
            return current

        avg_time = sum(self._mining_times) / len(self._mining_times)

        if avg_time < self.target_interval * 0.5:
            new_diff = min(current + 1, self.max_difficulty)
        elif avg_time > self.target_interval * 2.0:
            new_diff = max(current - 1, self.min_difficulty)
        else:
            new_diff = current

        if new_diff != current:
            logger.info(f"Difficulty adjusted: {current}   {new_diff} (avg mine time: {avg_time:.2f}s)")
        return new_diff


#  
# Blockchain Audit Ledger (Main Interface)
#  

class BlockchainAuditLedger:
    """Main interface for blockchain-based audit logging.

    Provides high-level methods for recording audit events,
    querying the ledger, and verifying integrity.

    Usage:
        ledger = BlockchainAuditLedger()
        ledger.start()

        # Record events
        ledger.record_event("user_login", actor="admin", target="auth_system")
        ledger.record_security_alert("brute_force_detected", target="ssh")

        # Query
        alerts = ledger.search(tx_type=TransactionType.SECURITY_ALERT)

        # Verify integrity
        is_valid, errors = ledger.verify()

        ledger.stop()
    """

    def __init__(
        self,
        difficulty: int = DEFAULT_DIFFICULTY,
        block_interval: float = BLOCK_INTERVAL_SECONDS,
        persist_dir: Optional[str] = None,
        secret_key: str = "aetheros-v3-blockchain-key",
    ):
        self.chain = BlockchainChain(difficulty=difficulty)
        self.pool = TransactionPool()
        self.consensus = ConsensusEngine(target_interval=block_interval)
        self._secret_key = secret_key
        self._persist_dir = persist_dir or os.path.expanduser("~/.aetheros/blockchain")
        self._block_interval = block_interval
        self._is_running = False
        self._mining_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._event_callbacks: List[Callable[[Block], None]] = []
        logger.info("BlockchainAuditLedger initialized")

    def start(self) -> None:
        """Start the background block mining process."""
        self._is_running = True
        self._mining_thread = threading.Thread(target=self._mining_loop, daemon=True)
        self._mining_thread.start()
        logger.info("Blockchain mining started")

    def stop(self) -> None:
        """Stop the mining process and persist the chain."""
        self._is_running = False
        if self._mining_thread:
            self._mining_thread.join(timeout=10.0)
        self._persist_chain()
        logger.info("Blockchain mining stopped")

    def _mining_loop(self) -> None:
        """Background loop that mines blocks at regular intervals."""
        while self._is_running:
            try:
                time.sleep(self._block_interval)
                if not self.pool.is_empty:
                    self._mine_pending()
            except Exception as e:
                logger.error(f"Mining loop error: {e}")

    def _mine_pending(self) -> Optional[Block]:
        """Mine a new block with pending transactions."""
        transactions = self.pool.drain()
        if not transactions:
            return None

        start = time.time()
        block = self.chain.add_block(transactions)
        mining_time = time.time() - start

        self.consensus.record_mining_time(mining_time)
        new_difficulty = self.consensus.adjust_difficulty(self.chain.difficulty)
        self.chain.difficulty = new_difficulty

        # Notify callbacks
        for cb in self._event_callbacks:
            try:
                cb(block)
            except Exception as e:
                logger.error(f"Block callback error: {e}")

        return block

    def record_event(
        self,
        action: str,
        actor: str = "system",
        target: str = "",
        data: Optional[Dict[str, Any]] = None,
        severity: str = "info",
        tx_type: TransactionType = TransactionType.SYSTEM_EVENT,
    ) -> str:
        """Record an audit event. Returns transaction ID."""
        tx = AuditTransaction(
            tx_type=tx_type,
            actor=actor,
            action=action,
            target=target,
            data=data or {},
            severity=severity,
        )
        tx.sign(self._secret_key)
        self.pool.add(tx)
        return tx.tx_id

    def record_security_alert(
        self,
        action: str,
        target: str = "",
        data: Optional[Dict[str, Any]] = None,
        severity: str = "critical",
    ) -> str:
        return self.record_event(
            action=action, target=target, data=data,
            severity=severity, tx_type=TransactionType.SECURITY_ALERT,
        )

    def record_access(
        self,
        action: str,
        actor: str,
        target: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.record_event(
            action=action, actor=actor, target=target, data=data,
            tx_type=TransactionType.ACCESS_LOG,
        )

    def record_config_change(
        self,
        action: str,
        actor: str = "system",
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.record_event(
            action=action, actor=actor, data=data,
            tx_type=TransactionType.CONFIG_CHANGE,
        )

    def record_honeypot_trigger(
        self,
        action: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.record_event(
            action=action, data=data, severity="critical",
            tx_type=TransactionType.HONEYPOT_TRIGGER,
        )

    def force_mine(self) -> Optional[Block]:
        """Force mine pending transactions immediately."""
        return self._mine_pending()

    def verify(self) -> Tuple[bool, List[str]]:
        """Verify the entire blockchain integrity."""
        return self.chain.validate_chain()

    def search(
        self,
        tx_type: Optional[TransactionType] = None,
        actor: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search audit transactions."""
        txs = self.chain.search_transactions(
            tx_type=tx_type, actor=actor, severity=severity,
            since=since, limit=limit,
        )
        return [tx.to_dict() for tx in txs]

    def get_block(self, index: int) -> Optional[Dict[str, Any]]:
        block = self.chain.get_block(index)
        return block.to_dict() if block else None

    def get_chain_summary(self) -> Dict[str, Any]:
        is_valid, errors = self.chain.validate_chain()
        return {
            "chain_length": self.chain.length,
            "total_transactions": self.chain.total_transactions,
            "difficulty": self.chain.difficulty,
            "pending_transactions": self.pool.size,
            "is_valid": is_valid,
            "validation_errors": errors,
            "latest_block_hash": self.chain.get_latest_block().block_hash[:16] + "...",
            "is_mining": self._is_running,
        }

    def register_block_callback(self, callback: Callable[[Block], None]) -> None:
        self._event_callbacks.append(callback)

    def _persist_chain(self) -> bool:
        """Persist the blockchain to disk."""
        filepath = os.path.join(self._persist_dir, "chain.json")
        return self.chain.export_json(filepath)

    def _load_chain(self) -> bool:
        """Load the blockchain from disk."""
        filepath = os.path.join(self._persist_dir, "chain.json")
        if os.path.exists(filepath):
            return self.chain.import_json(filepath)
        return False

    def get_transaction_proof(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """Get a Merkle proof for a specific transaction."""
        for block in reversed(self.chain._chain):
            for i, tx in enumerate(block.transactions):
                if tx.tx_id == tx_id:
                    tree = MerkleTree(block.transactions)
                    proof = tree.get_proof(i)
                    return {
                        "block_index": block.index,
                        "block_hash": block.block_hash,
                        "tx_hash": tx.compute_hash(),
                        "merkle_root": tree.root,
                        "proof": [(h, d) for h, d in proof],
                        "verified": MerkleTree.verify_proof(
                            tx.compute_hash(), proof, tree.root
                        ),
                    }
        return None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def stats(self) -> Dict[str, Any]:
        return self.get_chain_summary()
