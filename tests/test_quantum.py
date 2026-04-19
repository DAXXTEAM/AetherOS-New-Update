"""Tests for the Quantum Engine."""
import math
import pytest
from core.quantum_engine import (
    QuantumCircuit, QuantumStateVector, BB84Protocol, QuantumRNG,
    Qubit, QuantumGate, GateType,
)


class TestQuantumStateVector:
    def test_initial_state(self):
        sv = QuantumStateVector(2)
        assert sv.amplitudes[0] == complex(1, 0)
        assert all(sv.amplitudes[i] == 0 for i in range(1, 4))

    def test_measure(self):
        sv = QuantumStateVector(1)
        result = sv.measure(0)
        assert result in (0, 1)

    def test_measure_all(self):
        sv = QuantumStateVector(3)
        results = sv.measure_all()
        assert len(results) == 3
        assert all(b in (0, 1) for b in results)

    def test_probabilities(self):
        sv = QuantumStateVector(1)
        probs = sv.get_probabilities()
        assert "0" in probs or "1" in probs
        total = sum(probs.values())
        assert abs(total - 1.0) < 0.01

    def test_entanglement_entropy(self):
        sv = QuantumStateVector(2)
        # Bell state: apply H then CNOT
        h_matrix = [
            [complex(1/math.sqrt(2)), complex(1/math.sqrt(2))],
            [complex(1/math.sqrt(2)), complex(-1/math.sqrt(2))],
        ]
        sv.apply_single_gate(h_matrix, 0)
        sv.apply_cnot(0, 1)
        entropy = sv.entanglement_entropy([0])
        assert entropy > 0  # Entangled state has positive entropy


class TestQuantumCircuit:
    def test_hadamard_equal_superposition(self):
        qc = QuantumCircuit(1)
        qc.h(0)
        probs = qc.state.get_probabilities()
        for key, prob in probs.items():
            assert abs(prob - 0.5) < 0.01

    def test_x_gate_flip(self):
        qc = QuantumCircuit(1)
        qc.x(0)
        probs = qc.state.get_probabilities()
        assert "1" in probs
        assert probs["1"] > 0.99

    def test_cnot_entanglement(self):
        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cnot(0, 1)
        probs = qc.state.get_probabilities()
        # Bell state: only |00> and |11>
        for key, prob in probs.items():
            assert key in ("00", "11")
            assert abs(prob - 0.5) < 0.01

    def test_measure(self):
        qc = QuantumCircuit(1)
        result = qc.measure(0)
        assert result == 0  # |0> state

    def test_run_shots(self):
        qc = QuantumCircuit(1)
        qc.h(0)
        counts = qc.run(shots=100)
        assert len(counts) > 0
        total = sum(counts.values())
        assert total == 100

    def test_rotation_gates(self):
        qc = QuantumCircuit(1)
        qc.rx(0, math.pi)
        # RX(pi) should flip |0> to |1>
        probs = qc.state.get_probabilities()
        assert "1" in probs
        assert probs["1"] > 0.99

    def test_get_status(self):
        qc = QuantumCircuit(2, name="test-circuit")
        qc.h(0)
        qc.cnot(0, 1)
        status = qc.get_status()
        assert status["num_qubits"] == 2
        assert status["gate_count"] == 2
        assert status["name"] == "test-circuit"


class TestBB84Protocol:
    def test_generate_key(self):
        bb84 = BB84Protocol(key_length=64)
        result = bb84.generate_key(error_rate=0.01)
        assert "key_hex" in result
        assert result["key_bits"] == 64
        assert result["secure"]

    def test_detect_eavesdropping(self):
        bb84 = BB84Protocol(key_length=64)
        result = bb84.generate_key(error_rate=0.25)
        assert not result["secure"]

    def test_key_length(self):
        bb84 = BB84Protocol(key_length=128)
        result = bb84.generate_key()
        assert result["key_bits"] == 128


class TestQuantumRNG:
    def test_random_bits(self):
        rng = QuantumRNG(num_qubits=4)
        bits = rng.random_bits(32)
        assert len(bits) == 32
        assert all(b in (0, 1) for b in bits)

    def test_random_int(self):
        rng = QuantumRNG()
        val = rng.random_int(0, 100)
        assert 0 <= val <= 100

    def test_random_bytes(self):
        rng = QuantumRNG()
        data = rng.random_bytes(16)
        assert len(data) == 16
        assert isinstance(data, bytes)

    def test_stats(self):
        rng = QuantumRNG()
        rng.random_bits(10)
        stats = rng.get_stats()
        assert stats["total_generated_bits"] == 10
