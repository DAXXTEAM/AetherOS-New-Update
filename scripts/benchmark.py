#!/usr/bin/env python3
"""AetherOS Performance Benchmark."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def benchmark_crypto():
    from security.crypto import QuantumSafeCrypto, AESEncryptor
    crypto = QuantumSafeCrypto()
    start = time.time()
    for _ in range(100):
        msg = crypto.encrypt("Hello AetherOS!")
    elapsed = time.time() - start
    return {"operation": "encrypt_100", "time_ms": round(elapsed * 1000, 2)}


def benchmark_quantum_circuit():
    from core.quantum_engine import QuantumCircuit
    start = time.time()
    for _ in range(10):
        qc = QuantumCircuit(4)
        qc.h(0).cnot(0, 1).h(2).cnot(2, 3)
        qc.run(shots=100)
    elapsed = time.time() - start
    return {"operation": "quantum_4q_10x100shots", "time_ms": round(elapsed * 1000, 2)}


def benchmark_hash_ring():
    from core.mesh import ConsistentHashRing
    ring = ConsistentHashRing(virtual_nodes=150)
    start = time.time()
    for i in range(100):
        ring.add_node(f"node-{i}")
    for i in range(10000):
        ring.get_node(f"key-{i}")
    elapsed = time.time() - start
    return {"operation": "hash_ring_100nodes_10k_lookups", "time_ms": round(elapsed * 1000, 2)}


def benchmark_knowledge_graph():
    from memory.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph()
    start = time.time()
    nodes = []
    for i in range(500):
        nid = kg.add_node(f"entity-{i}", "entity")
        nodes.append(nid)
    for i in range(499):
        kg.add_edge(nodes[i], nodes[i + 1], "relates_to")
    kg.shortest_path(nodes[0], nodes[100])
    elapsed = time.time() - start
    return {"operation": "kg_500nodes_bfs", "time_ms": round(elapsed * 1000, 2)}


def benchmark_force_layout():
    from gui.neural_map import NeuralChainGraph, NodeType
    graph = NeuralChainGraph()
    nodes_ids = []
    for i in range(50):
        nid = graph.add_node(f"N{i}", NodeType.TASK)
        nodes_ids.append(nid)
    for i in range(49):
        graph.add_edge(nodes_ids[i], nodes_ids[i + 1])
    start = time.time()
    graph.layout(max_iterations=100)
    elapsed = time.time() - start
    return {"operation": "force_layout_50nodes", "time_ms": round(elapsed * 1000, 2)}


def main():
    print("\nAetherOS Performance Benchmark\n" + "=" * 40)
    benchmarks = [
        benchmark_crypto,
        benchmark_quantum_circuit,
        benchmark_hash_ring,
        benchmark_knowledge_graph,
        benchmark_force_layout,
    ]
    for bench in benchmarks:
        try:
            result = bench()
            print(f"  ✅ {result['operation']}: {result['time_ms']}ms")
        except Exception as e:
            print(f"  ❌ {bench.__name__}: {e}")
    print("=" * 40)


if __name__ == "__main__":
    main()
