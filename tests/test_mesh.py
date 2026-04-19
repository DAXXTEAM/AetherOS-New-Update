"""Tests for the Distributed Mesh Network."""
import pytest
from core.mesh import (
    MeshNetwork, ConsistentHashRing, WorkStealingScheduler,
    MembershipProtocol, MeshMessage, MeshTask, PeerInfo, PeerState,
    P2PDiscoveryService, TaskDistributionStrategy,
)


class TestConsistentHashRing:
    def test_add_and_get(self):
        ring = ConsistentHashRing(virtual_nodes=10)
        ring.add_node("node-1")
        ring.add_node("node-2")
        result = ring.get_node("task-123")
        assert result in ("node-1", "node-2")

    def test_consistency(self):
        ring = ConsistentHashRing(virtual_nodes=50)
        ring.add_node("node-1")
        ring.add_node("node-2")
        ring.add_node("node-3")
        r1 = ring.get_node("key-abc")
        r2 = ring.get_node("key-abc")
        assert r1 == r2

    def test_get_multiple_nodes(self):
        ring = ConsistentHashRing(virtual_nodes=20)
        for i in range(5):
            ring.add_node(f"node-{i}")
        nodes = ring.get_nodes_for_key("key-1", count=3)
        assert len(nodes) == 3
        assert len(set(nodes)) == 3  # All unique

    def test_remove_node(self):
        ring = ConsistentHashRing(virtual_nodes=10)
        ring.add_node("node-1")
        ring.add_node("node-2")
        ring.remove_node("node-1")
        result = ring.get_node("any-key")
        assert result == "node-2"

    def test_empty_ring(self):
        ring = ConsistentHashRing()
        assert ring.get_node("key") is None

    def test_distribution(self):
        ring = ConsistentHashRing(virtual_nodes=100)
        ring.add_node("a")
        ring.add_node("b")
        dist = ring.get_distribution()
        assert "a" in dist and "b" in dist


class TestMembershipProtocol:
    def test_add_peer(self):
        protocol = MembershipProtocol()
        peer = PeerInfo(hostname="test-node", address="10.0.0.1", port=51337)
        protocol.add_peer(peer)
        assert len(protocol.get_all_peers()) == 1

    def test_heartbeat(self):
        protocol = MembershipProtocol()
        peer = PeerInfo(hostname="test", address="10.0.0.1", port=51337, state=PeerState.ALIVE)
        protocol.add_peer(peer)
        protocol.record_heartbeat(peer.peer_id, load=0.5)
        peers = protocol.get_alive_peers()
        assert len(peers) == 1
        assert peers[0].load == 0.5

    def test_status(self):
        protocol = MembershipProtocol()
        status = protocol.get_status()
        assert "total_peers" in status
        assert "alive_peers" in status


class TestWorkStealingScheduler:
    def test_enqueue_dequeue(self):
        scheduler = WorkStealingScheduler("local-1")
        task = MeshTask(objective="Test task")
        scheduler.enqueue(task)
        assert scheduler.queue_size == 1
        dequeued = scheduler.dequeue()
        assert dequeued is not None
        assert dequeued.objective == "Test task"

    def test_complete_task(self):
        scheduler = WorkStealingScheduler("local-1")
        task = MeshTask(objective="Test")
        scheduler.enqueue(task)
        dequeued = scheduler.dequeue()
        assert scheduler.complete_task(dequeued.task_id, "done")
        assert scheduler.active_tasks == 0

    def test_fail_task_retry(self):
        scheduler = WorkStealingScheduler("local-1")
        task = MeshTask(objective="Test", max_retries=2)
        scheduler.enqueue(task)
        dequeued = scheduler.dequeue()
        scheduler.fail_task(dequeued.task_id, "error")
        assert scheduler.queue_size == 1  # Retried

    def test_stealable(self):
        scheduler = WorkStealingScheduler("local-1")
        for i in range(5):
            scheduler.enqueue(MeshTask(objective=f"task-{i}"))
        stolen = scheduler.get_stealable_tasks(2)
        assert len(stolen) == 2
        assert scheduler.queue_size == 3


class TestMeshMessage:
    def test_encode_decode(self):
        msg = MeshMessage(sender_id="node-1", message_type="heartbeat", payload={"load": 0.5})
        encoded = msg.encode()
        decoded = MeshMessage.decode(encoded)
        assert decoded is not None
        assert decoded.sender_id == "node-1"
        assert decoded.payload["load"] == 0.5

    def test_invalid_decode(self):
        result = MeshMessage.decode(b"invalid data")
        assert result is None


class TestMeshNetwork:
    def test_create_network(self):
        mesh = MeshNetwork(node_name="test-node")
        assert mesh.local_peer.hostname == "test-node"
        assert mesh.hash_ring.node_count == 1

    def test_distribute_task_local(self):
        mesh = MeshNetwork(node_name="test")
        task = MeshTask(objective="local task")
        assigned = mesh.distribute_task(task)
        assert assigned == mesh.local_peer.peer_id
        assert mesh.scheduler.queue_size == 1

    def test_get_topology(self):
        mesh = MeshNetwork(node_name="test")
        topo = mesh.get_mesh_topology()
        assert len(topo["nodes"]) == 1
        assert topo["nodes"][0]["is_local"]

    def test_get_status(self):
        mesh = MeshNetwork(node_name="test")
        status = mesh.get_status()
        assert "local_peer" in status
        assert "scheduler" in status
        assert "membership" in status
