"""Raft Consensus Protocol — Simplified Raft for distributed state agreement.

Implements leader election, log replication, and state machine application
for consistent distributed decisions across the AetherOS mesh.
"""
from __future__ import annotations

import logging
import random
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Optional

logger = logging.getLogger("aetheros.protocols.consensus")


class ConsensusState(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class LogEntry:
    """A log entry in the replicated log."""
    term: int = 0
    index: int = 0
    command: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"term": self.term, "index": self.index, "command": self.command}


@dataclass
class VoteRequest:
    term: int = 0
    candidate_id: str = ""
    last_log_index: int = 0
    last_log_term: int = 0


@dataclass
class VoteResponse:
    term: int = 0
    vote_granted: bool = False
    voter_id: str = ""


@dataclass
class AppendRequest:
    term: int = 0
    leader_id: str = ""
    prev_log_index: int = 0
    prev_log_term: int = 0
    entries: list[LogEntry] = field(default_factory=list)
    leader_commit: int = 0


@dataclass
class AppendResponse:
    term: int = 0
    success: bool = False
    match_index: int = 0
    responder_id: str = ""


class RaftConsensus:
    """Simplified Raft consensus implementation for AetherOS mesh."""

    def __init__(
        self,
        node_id: str = "",
        peer_ids: Optional[list[str]] = None,
        election_timeout_range: tuple[float, float] = (1.5, 3.0),
        heartbeat_interval: float = 0.5,
    ):
        self.node_id = node_id or uuid.uuid4().hex[:10]
        self.peer_ids = peer_ids or []
        self.election_timeout_range = election_timeout_range
        self.heartbeat_interval = heartbeat_interval

        self.state = ConsensusState.FOLLOWER
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.leader_id: Optional[str] = None
        self.log: list[LogEntry] = []
        self.commit_index = 0
        self.last_applied = 0

        self._next_index: dict[str, int] = {}
        self._match_index: dict[str, int] = {}
        self._votes_received: set[str] = set()

        self._election_timeout = self._random_timeout()
        self._last_heartbeat = time.time()
        self._running = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        self._state_machine: dict[str, Any] = {}
        self._on_leader_change: Optional[Callable] = None
        self._on_commit: Optional[Callable] = None

        self._stats = {
            "elections": 0,
            "terms": 0,
            "entries_committed": 0,
            "heartbeats_sent": 0,
        }

    def _random_timeout(self) -> float:
        low, high = self.election_timeout_range
        return random.uniform(low, high)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"Raft consensus started: {self.node_id}")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        while self._running:
            with self._lock:
                if self.state == ConsensusState.FOLLOWER:
                    self._follower_tick()
                elif self.state == ConsensusState.CANDIDATE:
                    self._candidate_tick()
                elif self.state == ConsensusState.LEADER:
                    self._leader_tick()
            time.sleep(0.1)

    def _follower_tick(self) -> None:
        if time.time() - self._last_heartbeat > self._election_timeout:
            self._become_candidate()

    def _candidate_tick(self) -> None:
        if len(self._votes_received) > (len(self.peer_ids) + 1) // 2:
            self._become_leader()
        elif time.time() - self._last_heartbeat > self._election_timeout:
            self._become_candidate()

    def _leader_tick(self) -> None:
        self._stats["heartbeats_sent"] += 1

    def _become_candidate(self) -> None:
        self.current_term += 1
        self.state = ConsensusState.CANDIDATE
        self.voted_for = self.node_id
        self._votes_received = {self.node_id}
        self._election_timeout = self._random_timeout()
        self._last_heartbeat = time.time()
        self._stats["elections"] += 1
        logger.info(f"Node {self.node_id} became candidate (term {self.current_term})")

    def _become_leader(self) -> None:
        self.state = ConsensusState.LEADER
        self.leader_id = self.node_id
        for peer in self.peer_ids:
            self._next_index[peer] = len(self.log)
            self._match_index[peer] = 0
        self._stats["terms"] += 1
        logger.info(f"Node {self.node_id} became leader (term {self.current_term})")
        if self._on_leader_change:
            self._on_leader_change(self.node_id, self.current_term)

    def handle_vote_request(self, request: VoteRequest) -> VoteResponse:
        with self._lock:
            if request.term < self.current_term:
                return VoteResponse(term=self.current_term, vote_granted=False, voter_id=self.node_id)
            if request.term > self.current_term:
                self.current_term = request.term
                self.state = ConsensusState.FOLLOWER
                self.voted_for = None
            if self.voted_for is None or self.voted_for == request.candidate_id:
                self.voted_for = request.candidate_id
                self._last_heartbeat = time.time()
                return VoteResponse(term=self.current_term, vote_granted=True, voter_id=self.node_id)
            return VoteResponse(term=self.current_term, vote_granted=False, voter_id=self.node_id)

    def handle_vote_response(self, response: VoteResponse) -> None:
        with self._lock:
            if response.term > self.current_term:
                self.current_term = response.term
                self.state = ConsensusState.FOLLOWER
                return
            if response.vote_granted and self.state == ConsensusState.CANDIDATE:
                self._votes_received.add(response.voter_id)

    def handle_append_request(self, request: AppendRequest) -> AppendResponse:
        with self._lock:
            if request.term < self.current_term:
                return AppendResponse(term=self.current_term, success=False, responder_id=self.node_id)
            self.current_term = request.term
            self.leader_id = request.leader_id
            self.state = ConsensusState.FOLLOWER
            self._last_heartbeat = time.time()

            # Append entries
            for entry in request.entries:
                if entry.index < len(self.log):
                    self.log[entry.index] = entry
                else:
                    self.log.append(entry)

            if request.leader_commit > self.commit_index:
                self.commit_index = min(request.leader_commit, len(self.log) - 1 if self.log else 0)
                self._apply_committed()

            return AppendResponse(
                term=self.current_term,
                success=True,
                match_index=len(self.log) - 1 if self.log else 0,
                responder_id=self.node_id,
            )

    def propose(self, command: str, data: Optional[dict] = None) -> Optional[LogEntry]:
        """Propose a new entry (must be leader)."""
        with self._lock:
            if self.state != ConsensusState.LEADER:
                return None
            entry = LogEntry(
                term=self.current_term,
                index=len(self.log),
                command=command,
                data=data or {},
            )
            self.log.append(entry)
            return entry

    def _apply_committed(self) -> None:
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            if self.last_applied < len(self.log):
                entry = self.log[self.last_applied]
                self._state_machine[entry.command] = entry.data
                self._stats["entries_committed"] += 1
                if self._on_commit:
                    self._on_commit(entry)

    def on_leader_change(self, callback: Callable) -> None:
        self._on_leader_change = callback

    def on_commit(self, callback: Callable) -> None:
        self._on_commit = callback

    def get_status(self) -> dict:
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "term": self.current_term,
            "leader": self.leader_id,
            "log_length": len(self.log),
            "commit_index": self.commit_index,
            "last_applied": self.last_applied,
            "peers": self.peer_ids,
            "stats": self._stats,
        }
