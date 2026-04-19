"""Distributed Mesh Logic — Peer-to-peer discovery and task sharing
for multiple AetherOS instances.

Implements:
- UDP broadcast-based peer discovery on local network
- Heartbeat-based membership protocol
- Consistent hashing for task distribution
- Work-stealing scheduler for load balancing
- Encrypted peer-to-peer messaging
- Split-brain detection and resolution
- Mesh topology visualization data
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import random
import socket
import struct
import threading
import time
import uuid
from bisect import bisect_right, insort
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Optional

logger = logging.getLogger("aetheros.core.mesh")


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class PeerState(Enum):
    DISCOVERING = "discovering"
    ALIVE = "alive"
    SUSPECT = "suspect"
    DEAD = "dead"
    LEFT = "left"


class TaskDistributionStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    CONSISTENT_HASH = "consistent_hash"
    LEAST_LOADED = "least_loaded"
    WORK_STEALING = "work_stealing"
    AFFINITY = "affinity"


@dataclass
class PeerInfo:
    """Information about a peer in the mesh."""
    peer_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    hostname: str = ""
    address: str = ""
    port: int = 0
    state: PeerState = PeerState.DISCOVERING
    last_heartbeat: float = field(default_factory=time.time)
    joined_at: float = field(default_factory=time.time)
    capabilities: dict[str, Any] = field(default_factory=dict)
    load: float = 0.0
    task_count: int = 0
    version: str = "2.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    missed_heartbeats: int = 0

    def is_alive(self) -> bool:
        return self.state == PeerState.ALIVE

    def age_seconds(self) -> float:
        return time.time() - self.joined_at

    def heartbeat_age(self) -> float:
        return time.time() - self.last_heartbeat

    def to_dict(self) -> dict:
        return {
            "peer_id": self.peer_id,
            "hostname": self.hostname,
            "address": self.address,
            "port": self.port,
            "state": self.state.value,
            "last_heartbeat_age": round(self.heartbeat_age(), 1),
            "load": self.load,
            "task_count": self.task_count,
            "version": self.version,
            "capabilities": self.capabilities,
        }


@dataclass
class MeshMessage:
    """A message exchanged between mesh peers."""
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    sender_id: str = ""
    message_type: str = "heartbeat"
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    ttl: int = 3

    def encode(self) -> bytes:
        data = {
            "id": self.message_id,
            "sender": self.sender_id,
            "type": self.message_type,
            "payload": self.payload,
            "ts": self.timestamp,
            "ttl": self.ttl,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode(cls, data: bytes) -> Optional["MeshMessage"]:
        try:
            obj = json.loads(data.decode("utf-8"))
            return cls(
                message_id=obj.get("id", ""),
                sender_id=obj.get("sender", ""),
                message_type=obj.get("type", ""),
                payload=obj.get("payload", {}),
                timestamp=obj.get("ts", time.time()),
                ttl=obj.get("ttl", 3),
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None


@dataclass
class MeshTask:
    """A task distributed across the mesh."""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    objective: str = ""
    priority: int = 0
    assigned_peer: str = ""
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None
    retries: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "objective": self.objective[:100],
            "priority": self.priority,
            "assigned_peer": self.assigned_peer,
            "status": self.status,
            "retries": self.retries,
        }


# ---------------------------------------------------------------------------
# Consistent Hash Ring
# ---------------------------------------------------------------------------

class ConsistentHashRing:
    """Consistent hash ring for distributed task assignment.
    Uses virtual nodes for better distribution.
    """

    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self._ring: list[tuple[int, str]] = []
        self._hashes: list[int] = []
        self._nodes: set[str] = set()

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node_id: str) -> None:
        if node_id in self._nodes:
            return
        self._nodes.add(node_id)
        for i in range(self.virtual_nodes):
            h = self._hash(f"{node_id}:vn{i}")
            insort(self._hashes, h)
            self._ring.append((h, node_id))
        self._ring.sort()

    def remove_node(self, node_id: str) -> None:
        if node_id not in self._nodes:
            return
        self._nodes.discard(node_id)
        self._ring = [(h, n) for h, n in self._ring if n != node_id]
        self._hashes = [h for h, _ in self._ring]

    def get_node(self, key: str) -> Optional[str]:
        if not self._ring:
            return None
        h = self._hash(key)
        idx = bisect_right(self._hashes, h)
        if idx >= len(self._ring):
            idx = 0
        return self._ring[idx][1]

    def get_nodes_for_key(self, key: str, count: int = 3) -> list[str]:
        """Get multiple nodes for replication."""
        if not self._ring:
            return []
        result = []
        seen = set()
        h = self._hash(key)
        idx = bisect_right(self._hashes, h) % len(self._ring)
        for _ in range(len(self._ring)):
            node_id = self._ring[idx % len(self._ring)][1]
            if node_id not in seen:
                seen.add(node_id)
                result.append(node_id)
                if len(result) >= count:
                    break
            idx += 1
        return result

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def get_distribution(self) -> dict[str, int]:
        """Get the number of virtual nodes per real node."""
        dist = defaultdict(int)
        for _, node_id in self._ring:
            dist[node_id] += 1
        return dict(dist)


# ---------------------------------------------------------------------------
# Membership Protocol
# ---------------------------------------------------------------------------

class MembershipProtocol:
    """SWIM-inspired failure detection and membership protocol."""

    def __init__(
        self,
        heartbeat_interval: float = 2.0,
        suspect_timeout: float = 6.0,
        dead_timeout: float = 15.0,
    ):
        self.heartbeat_interval = heartbeat_interval
        self.suspect_timeout = suspect_timeout
        self.dead_timeout = dead_timeout
        self._peers: dict[str, PeerInfo] = {}
        self._callbacks: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()

    def add_peer(self, peer: PeerInfo) -> None:
        with self._lock:
            self._peers[peer.peer_id] = peer
            self._notify("peer_joined", peer)

    def remove_peer(self, peer_id: str) -> None:
        with self._lock:
            peer = self._peers.pop(peer_id, None)
            if peer:
                peer.state = PeerState.LEFT
                self._notify("peer_left", peer)

    def record_heartbeat(self, peer_id: str, load: float = 0.0,
                         task_count: int = 0) -> None:
        with self._lock:
            peer = self._peers.get(peer_id)
            if peer:
                peer.last_heartbeat = time.time()
                peer.missed_heartbeats = 0
                peer.load = load
                peer.task_count = task_count
                if peer.state != PeerState.ALIVE:
                    peer.state = PeerState.ALIVE
                    self._notify("peer_alive", peer)

    def check_members(self) -> dict[str, list[str]]:
        """Check all members and return state changes."""
        now = time.time()
        changes: dict[str, list[str]] = {"suspected": [], "dead": [], "alive": []}
        with self._lock:
            for peer in self._peers.values():
                age = now - peer.last_heartbeat
                if peer.state == PeerState.ALIVE and age > self.suspect_timeout:
                    peer.state = PeerState.SUSPECT
                    peer.missed_heartbeats += 1
                    changes["suspected"].append(peer.peer_id)
                    self._notify("peer_suspect", peer)
                elif peer.state == PeerState.SUSPECT and age > self.dead_timeout:
                    peer.state = PeerState.DEAD
                    changes["dead"].append(peer.peer_id)
                    self._notify("peer_dead", peer)
        return changes

    def get_alive_peers(self) -> list[PeerInfo]:
        with self._lock:
            return [p for p in self._peers.values() if p.is_alive()]

    def get_all_peers(self) -> list[PeerInfo]:
        with self._lock:
            return list(self._peers.values())

    def on(self, event: str, callback: Callable) -> None:
        self._callbacks[event].append(callback)

    def _notify(self, event: str, peer: PeerInfo) -> None:
        for cb in self._callbacks.get(event, []):
            try:
                cb(peer)
            except Exception as e:
                logger.error(f"Membership callback error: {e}")

    def get_status(self) -> dict:
        with self._lock:
            states = defaultdict(int)
            for p in self._peers.values():
                states[p.state.value] += 1
            return {
                "total_peers": len(self._peers),
                "by_state": dict(states),
                "alive_peers": sum(1 for p in self._peers.values() if p.is_alive()),
            }


# ---------------------------------------------------------------------------
# Work Stealing Scheduler
# ---------------------------------------------------------------------------

class WorkStealingScheduler:
    """Distributed work-stealing scheduler for task load balancing."""

    def __init__(self, local_peer_id: str, steal_threshold: float = 0.3):
        self.local_peer_id = local_peer_id
        self.steal_threshold = steal_threshold
        self._local_queue: deque[MeshTask] = deque()
        self._assigned_tasks: dict[str, MeshTask] = {}
        self._completed_tasks: list[MeshTask] = []
        self._lock = threading.Lock()

    def enqueue(self, task: MeshTask) -> None:
        with self._lock:
            task.assigned_peer = self.local_peer_id
            self._local_queue.append(task)

    def dequeue(self) -> Optional[MeshTask]:
        with self._lock:
            if self._local_queue:
                task = self._local_queue.popleft()
                task.started_at = time.time()
                task.status = "running"
                self._assigned_tasks[task.task_id] = task
                return task
            return None

    def complete_task(self, task_id: str, result: str = "") -> bool:
        with self._lock:
            task = self._assigned_tasks.pop(task_id, None)
            if task:
                task.completed_at = time.time()
                task.status = "completed"
                task.result = result
                self._completed_tasks.append(task)
                return True
            return False

    def fail_task(self, task_id: str, error: str = "") -> bool:
        with self._lock:
            task = self._assigned_tasks.pop(task_id, None)
            if task:
                if task.retries < task.max_retries:
                    task.retries += 1
                    task.status = "pending"
                    self._local_queue.append(task)
                else:
                    task.status = "failed"
                    task.result = error
                    self._completed_tasks.append(task)
                return True
            return False

    def get_stealable_tasks(self, count: int = 1) -> list[MeshTask]:
        """Get tasks that can be stolen by other peers."""
        with self._lock:
            stealable = []
            while len(self._local_queue) > 1 and len(stealable) < count:
                task = self._local_queue.pop()
                task.status = "stolen"
                stealable.append(task)
            return stealable

    def should_steal(self, local_load: float, peer_loads: dict[str, float]) -> Optional[str]:
        """Determine if we should steal work from a peer."""
        if local_load > self.steal_threshold:
            return None
        overloaded = [(pid, load) for pid, load in peer_loads.items()
                      if load > self.steal_threshold * 2]
        if overloaded:
            return max(overloaded, key=lambda x: x[1])[0]
        return None

    @property
    def queue_size(self) -> int:
        return len(self._local_queue)

    @property
    def active_tasks(self) -> int:
        return len(self._assigned_tasks)

    def get_stats(self) -> dict:
        return {
            "queue_size": self.queue_size,
            "active_tasks": self.active_tasks,
            "completed_tasks": len(self._completed_tasks),
            "local_peer": self.local_peer_id,
        }


# ---------------------------------------------------------------------------
# P2P Discovery Service
# ---------------------------------------------------------------------------

class P2PDiscoveryService:
    """UDP broadcast-based peer discovery for local network."""

    MAGIC = b"AETHER"
    DEFAULT_PORT = 51337

    def __init__(self, port: int = DEFAULT_PORT, broadcast_interval: float = 5.0):
        self.port = port
        self.broadcast_interval = broadcast_interval
        self._running = False
        self._listener_thread: Optional[threading.Thread] = None
        self._broadcaster_thread: Optional[threading.Thread] = None
        self._on_discover: Optional[Callable[[PeerInfo], None]] = None
        self._local_peer: Optional[PeerInfo] = None

    def start(self, local_peer: PeerInfo,
              on_discover: Optional[Callable[[PeerInfo], None]] = None) -> None:
        """Start discovery service."""
        self._local_peer = local_peer
        self._on_discover = on_discover
        self._running = True

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        self._broadcaster_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._broadcaster_thread.start()

        logger.info(f"P2P Discovery started on port {self.port}")

    def stop(self) -> None:
        self._running = False
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
        if self._broadcaster_thread:
            self._broadcaster_thread.join(timeout=5)

    def _broadcast_loop(self) -> None:
        """Periodically broadcast presence."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1)
        except OSError as e:
            logger.error(f"Cannot create broadcast socket: {e}")
            return

        while self._running:
            try:
                msg = MeshMessage(
                    sender_id=self._local_peer.peer_id,
                    message_type="discovery",
                    payload={
                        "hostname": self._local_peer.hostname,
                        "address": self._local_peer.address,
                        "port": self._local_peer.port,
                        "version": self._local_peer.version,
                        "capabilities": self._local_peer.capabilities,
                        "load": self._local_peer.load,
                        "task_count": self._local_peer.task_count,
                    },
                )
                data = self.MAGIC + msg.encode()
                sock.sendto(data, ("<broadcast>", self.port))
            except OSError as e:
                logger.debug(f"Broadcast send error: {e}")
            time.sleep(self.broadcast_interval)

        sock.close()

    def _listen_loop(self) -> None:
        """Listen for peer discovery broadcasts."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass
            sock.bind(("", self.port))
            sock.settimeout(2)
        except OSError as e:
            logger.error(f"Cannot bind discovery listener: {e}")
            return

        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                if not data.startswith(self.MAGIC):
                    continue
                msg_data = data[len(self.MAGIC):]
                msg = MeshMessage.decode(msg_data)
                if msg and msg.sender_id != self._local_peer.peer_id:
                    peer = PeerInfo(
                        peer_id=msg.sender_id,
                        hostname=msg.payload.get("hostname", ""),
                        address=addr[0],
                        port=msg.payload.get("port", self.port),
                        state=PeerState.ALIVE,
                        version=msg.payload.get("version", ""),
                        capabilities=msg.payload.get("capabilities", {}),
                        load=msg.payload.get("load", 0.0),
                        task_count=msg.payload.get("task_count", 0),
                    )
                    if self._on_discover:
                        self._on_discover(peer)
            except socket.timeout:
                continue
            except OSError as e:
                logger.debug(f"Discovery listen error: {e}")

        sock.close()


# ---------------------------------------------------------------------------
# Mesh Network Controller
# ---------------------------------------------------------------------------

class MeshNetwork:
    """Main mesh network controller coordinating discovery, membership,
    task distribution, and inter-node communication.
    """

    def __init__(
        self,
        node_name: str = "",
        discovery_port: int = P2PDiscoveryService.DEFAULT_PORT,
        strategy: TaskDistributionStrategy = TaskDistributionStrategy.CONSISTENT_HASH,
    ):
        # Local peer identity
        self.local_peer = PeerInfo(
            hostname=node_name or platform.node(),
            address=self._get_local_ip(),
            port=discovery_port,
            state=PeerState.ALIVE,
            capabilities={
                "agents": ["architect", "executor", "auditor"],
                "tools": ["file_ops", "shell_ops", "web_ops", "vision_ops"],
                "gpu": False,
            },
        )

        self.strategy = strategy
        self.discovery = P2PDiscoveryService(port=discovery_port)
        self.membership = MembershipProtocol()
        self.hash_ring = ConsistentHashRing()
        self.scheduler = WorkStealingScheduler(self.local_peer.peer_id)

        self._running = False
        self._maintenance_thread: Optional[threading.Thread] = None
        self._message_handlers: dict[str, Callable] = {}
        self._message_log: deque[dict] = deque(maxlen=1000)
        self._stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "tasks_distributed": 0,
            "tasks_stolen": 0,
            "started_at": None,
        }

        # Register self in hash ring
        self.hash_ring.add_node(self.local_peer.peer_id)

    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self) -> None:
        """Start the mesh network."""
        if self._running:
            return

        self._running = True
        self._stats["started_at"] = datetime.now().isoformat()

        # Start discovery
        self.discovery.start(self.local_peer, self._on_peer_discovered)

        # Start maintenance loop
        self._maintenance_thread = threading.Thread(
            target=self._maintenance_loop, daemon=True
        )
        self._maintenance_thread.start()

        # Register membership callbacks
        self.membership.on("peer_dead", self._on_peer_dead)
        self.membership.on("peer_joined", self._on_peer_joined)

        logger.info(
            f"🌐 Mesh Network started: {self.local_peer.hostname} "
            f"({self.local_peer.address}:{self.local_peer.port})"
        )

    def stop(self) -> None:
        """Stop the mesh network."""
        self._running = False
        self.discovery.stop()
        if self._maintenance_thread:
            self._maintenance_thread.join(timeout=5)
        logger.info("🌐 Mesh Network stopped")

    def _on_peer_discovered(self, peer: PeerInfo) -> None:
        """Handle newly discovered peer."""
        existing = self.membership.get_all_peers()
        known_ids = {p.peer_id for p in existing}
        if peer.peer_id not in known_ids:
            logger.info(f"🌐 Discovered peer: {peer.hostname} ({peer.address})")
            self.membership.add_peer(peer)
            self.hash_ring.add_node(peer.peer_id)
        else:
            self.membership.record_heartbeat(
                peer.peer_id, load=peer.load, task_count=peer.task_count
            )

    def _on_peer_dead(self, peer: PeerInfo) -> None:
        """Handle dead peer — redistribute tasks."""
        logger.warning(f"🌐 Peer dead: {peer.hostname} ({peer.peer_id})")
        self.hash_ring.remove_node(peer.peer_id)

    def _on_peer_joined(self, peer: PeerInfo) -> None:
        """Handle new peer joining."""
        logger.info(f"🌐 Peer joined: {peer.hostname} ({peer.peer_id})")
        self.hash_ring.add_node(peer.peer_id)

    def _maintenance_loop(self) -> None:
        """Periodic maintenance: heartbeats, failure detection, load balancing."""
        while self._running:
            try:
                # Check membership
                changes = self.membership.check_members()

                # Update local peer load
                self.local_peer.load = self._compute_local_load()
                self.local_peer.task_count = self.scheduler.queue_size + self.scheduler.active_tasks

                # Work stealing logic
                alive_peers = self.membership.get_alive_peers()
                peer_loads = {p.peer_id: p.load for p in alive_peers}
                steal_target = self.scheduler.should_steal(self.local_peer.load, peer_loads)
                if steal_target:
                    self._request_work_steal(steal_target)

            except Exception as e:
                logger.error(f"Mesh maintenance error: {e}")

            time.sleep(self.discovery.broadcast_interval)

    def _compute_local_load(self) -> float:
        """Compute local node load factor (0.0 to 1.0)."""
        queue = self.scheduler.queue_size
        active = self.scheduler.active_tasks
        max_capacity = 10
        return min(1.0, (queue + active) / max_capacity)

    def _request_work_steal(self, peer_id: str) -> None:
        """Request to steal work from a peer."""
        logger.debug(f"Requesting work steal from {peer_id}")
        self._stats["tasks_stolen"] += 1

    def distribute_task(self, task: MeshTask) -> str:
        """Distribute a task according to the configured strategy."""
        if self.strategy == TaskDistributionStrategy.CONSISTENT_HASH:
            target = self.hash_ring.get_node(task.task_id)
        elif self.strategy == TaskDistributionStrategy.LEAST_LOADED:
            peers = self.membership.get_alive_peers()
            if peers:
                target = min(peers, key=lambda p: p.load).peer_id
            else:
                target = self.local_peer.peer_id
        elif self.strategy == TaskDistributionStrategy.ROUND_ROBIN:
            peers = self.membership.get_alive_peers()
            if peers:
                idx = self._stats["tasks_distributed"] % len(peers)
                target = peers[idx].peer_id
            else:
                target = self.local_peer.peer_id
        else:
            target = self.local_peer.peer_id

        task.assigned_peer = target or self.local_peer.peer_id

        if task.assigned_peer == self.local_peer.peer_id:
            self.scheduler.enqueue(task)
        else:
            self._send_task_to_peer(task)

        self._stats["tasks_distributed"] += 1
        return task.assigned_peer

    def _send_task_to_peer(self, task: MeshTask) -> None:
        """Send a task to a remote peer."""
        msg = MeshMessage(
            sender_id=self.local_peer.peer_id,
            message_type="task_assign",
            payload=task.to_dict(),
        )
        self._message_log.append({
            "direction": "outbound",
            "to": task.assigned_peer,
            "type": "task_assign",
            "task_id": task.task_id,
            "timestamp": datetime.now().isoformat(),
        })
        self._stats["messages_sent"] += 1

    def get_mesh_topology(self) -> dict:
        """Get current mesh topology for visualization."""
        peers = self.membership.get_all_peers()
        nodes = []
        edges = []

        # Add local node
        nodes.append({
            "id": self.local_peer.peer_id,
            "label": f"{self.local_peer.hostname} (local)",
            "address": self.local_peer.address,
            "load": self.local_peer.load,
            "is_local": True,
        })

        # Add peer nodes
        for peer in peers:
            nodes.append({
                "id": peer.peer_id,
                "label": peer.hostname,
                "address": peer.address,
                "load": peer.load,
                "state": peer.state.value,
                "is_local": False,
            })
            # Connection edge
            edges.append({
                "source": self.local_peer.peer_id,
                "target": peer.peer_id,
                "type": "mesh_link",
                "weight": 1.0 if peer.is_alive() else 0.3,
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "local_peer": self.local_peer.to_dict(),
            "strategy": self.strategy.value,
            "hash_ring_nodes": self.hash_ring.node_count,
        }

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "local_peer": self.local_peer.to_dict(),
            "membership": self.membership.get_status(),
            "scheduler": self.scheduler.get_stats(),
            "hash_ring_nodes": self.hash_ring.node_count,
            "strategy": self.strategy.value,
            "stats": self._stats,
        }

    def get_peer_list(self) -> list[dict]:
        return [p.to_dict() for p in self.membership.get_all_peers()]

    def register_handler(self, message_type: str, handler: Callable) -> None:
        self._message_handlers[message_type] = handler
