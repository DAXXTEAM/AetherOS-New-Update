"""Tests for AetherOS Blockchain Audit Ledger."""
import pytest
import json
import time
from security.blockchain_logs import (
    BlockchainAuditLedger, BlockchainChain, Block, AuditTransaction,
    TransactionType, MerkleTree, TransactionPool, ConsensusEngine,
    BlockStatus, GENESIS_PREV_HASH,
)


class TestAuditTransaction:
    def test_create_transaction(self):
        tx = AuditTransaction(
            tx_type=TransactionType.SYSTEM_EVENT,
            actor="admin",
            action="test_action",
            target="test_target",
        )
        assert tx.tx_id
        assert tx.actor == "admin"
        assert tx.action == "test_action"

    def test_transaction_hash_deterministic(self):
        tx = AuditTransaction(
            tx_id="fixed-id",
            timestamp="2025-01-01T00:00:00",
            action="test",
        )
        h1 = tx.compute_hash()
        h2 = tx.compute_hash()
        assert h1 == h2
        assert len(h1) == 64

    def test_transaction_signature(self):
        tx = AuditTransaction(action="test_action", target="test_target")
        tx.sign("secret-key")
        assert tx.signature
        assert tx.verify_signature("secret-key")
        assert not tx.verify_signature("wrong-key")

    def test_transaction_serialization(self):
        tx = AuditTransaction(
            tx_type=TransactionType.SECURITY_ALERT,
            actor="sentinel",
            action="threat_detected",
        )
        d = tx.to_dict()
        assert d["tx_type"] == "security_alert"
        assert d["actor"] == "sentinel"

        tx2 = AuditTransaction.from_dict(d)
        assert tx2.tx_type == TransactionType.SECURITY_ALERT
        assert tx2.actor == "sentinel"


class TestMerkleTree:
    def test_empty_tree(self):
        tree = MerkleTree([])
        assert tree.root

    def test_single_transaction(self):
        tx = AuditTransaction(action="test")
        tree = MerkleTree([tx])
        assert tree.root
        assert tree.leaf_count == 1

    def test_multiple_transactions(self):
        txs = [AuditTransaction(action=f"test_{i}") for i in range(5)]
        tree = MerkleTree(txs)
        assert tree.root
        assert tree.leaf_count == 5
        assert tree.depth > 1

    def test_proof_verification(self):
        txs = [AuditTransaction(action=f"test_{i}") for i in range(4)]
        tree = MerkleTree(txs)
        proof = tree.get_proof(0)
        assert len(proof) > 0
        verified = MerkleTree.verify_proof(txs[0].compute_hash(), proof, tree.root)
        assert verified

    def test_tamper_detection(self):
        txs = [AuditTransaction(action=f"test_{i}") for i in range(4)]
        tree = MerkleTree(txs)
        proof = tree.get_proof(0)
        fake_hash = "0" * 64
        verified = MerkleTree.verify_proof(fake_hash, proof, tree.root)
        assert not verified


class TestBlock:
    def test_create_block(self):
        tx = AuditTransaction(action="test")
        block = Block(index=1, transactions=[tx])
        assert block.index == 1
        assert len(block.transactions) == 1
        assert block.merkle_root

    def test_mine_block(self):
        tx = AuditTransaction(action="test")
        block = Block(index=1, transactions=[tx], difficulty=1)
        nonce = block.mine()
        assert block.block_hash.startswith("0")
        assert nonce >= 0

    def test_validate_block(self):
        tx = AuditTransaction(action="test")
        block = Block(index=1, transactions=[tx], difficulty=1)
        block.mine()
        assert block.validate() == BlockStatus.VALID

    def test_block_serialization(self):
        tx = AuditTransaction(action="test")
        block = Block(index=1, transactions=[tx], difficulty=1)
        block.mine()
        d = block.to_dict()
        block2 = Block.from_dict(d)
        assert block2.index == 1
        assert block2.block_hash == block.block_hash


class TestBlockchainChain:
    def test_genesis_block(self):
        chain = BlockchainChain(difficulty=1)
        assert chain.length == 1
        genesis = chain.get_block(0)
        assert genesis.index == 0

    def test_add_block(self):
        chain = BlockchainChain(difficulty=1)
        tx = AuditTransaction(action="test_event")
        block = chain.add_block([tx])
        assert chain.length == 2
        assert block.index == 1

    def test_chain_validation(self):
        chain = BlockchainChain(difficulty=1)
        for i in range(3):
            tx = AuditTransaction(action=f"event_{i}")
            chain.add_block([tx])
        is_valid, errors = chain.validate_chain()
        assert is_valid
        assert len(errors) == 0

    def test_search_transactions(self):
        chain = BlockchainChain(difficulty=1)
        tx1 = AuditTransaction(
            tx_type=TransactionType.SECURITY_ALERT,
            action="alert",
        )
        tx2 = AuditTransaction(
            tx_type=TransactionType.ACCESS_LOG,
            action="login",
        )
        chain.add_block([tx1, tx2])
        results = chain.search_transactions(tx_type=TransactionType.SECURITY_ALERT)
        assert any(r.action == "alert" for r in results)


class TestTransactionPool:
    def test_add_and_drain(self):
        pool = TransactionPool()
        tx1 = AuditTransaction(action="test1")
        tx2 = AuditTransaction(action="test2")
        pool.add(tx1)
        pool.add(tx2)
        assert pool.size == 2
        drained = pool.drain(1)
        assert len(drained) == 1
        assert pool.size == 1

    def test_duplicate_prevention(self):
        pool = TransactionPool()
        tx = AuditTransaction(action="test")
        assert pool.add(tx)
        assert not pool.add(tx)  # Duplicate
        assert pool.size == 1


class TestBlockchainAuditLedger:
    def test_record_event(self):
        ledger = BlockchainAuditLedger(difficulty=1, block_interval=1.0)
        tx_id = ledger.record_event("test_event", actor="test")
        assert tx_id
        assert ledger.pool.size == 1

    def test_force_mine(self):
        ledger = BlockchainAuditLedger(difficulty=1)
        ledger.record_event("event_1")
        ledger.record_event("event_2")
        block = ledger.force_mine()
        assert block is not None
        assert block.index == 1
        assert len(block.transactions) == 2

    def test_verify_chain(self):
        ledger = BlockchainAuditLedger(difficulty=1)
        ledger.record_event("event_1")
        ledger.force_mine()
        is_valid, errors = ledger.verify()
        assert is_valid

    def test_chain_summary(self):
        ledger = BlockchainAuditLedger(difficulty=1)
        summary = ledger.get_chain_summary()
        assert summary["chain_length"] == 1
        assert summary["is_valid"]

    def test_record_multiple_types(self):
        ledger = BlockchainAuditLedger(difficulty=1)
        ledger.record_security_alert("breach_attempt")
        ledger.record_access("login", actor="admin", target="console")
        ledger.record_config_change("update_policy")
        ledger.record_honeypot_trigger("file_accessed")
        assert ledger.pool.size == 4
        block = ledger.force_mine()
        assert len(block.transactions) == 4

    def test_transaction_proof(self):
        ledger = BlockchainAuditLedger(difficulty=1)
        tx_id = ledger.record_event("provable_event")
        ledger.force_mine()
        proof = ledger.get_transaction_proof(tx_id)
        assert proof is not None
        assert proof["verified"]

    def test_search(self):
        ledger = BlockchainAuditLedger(difficulty=1)
        ledger.record_security_alert("alert_1")
        ledger.record_event("normal_event")
        ledger.force_mine()
        alerts = ledger.search(tx_type=TransactionType.SECURITY_ALERT)
        assert len(alerts) >= 1
        assert alerts[0]["tx_type"] == "security_alert"
