"""Knowledge Graph — Semantic knowledge storage and reasoning."""
from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("aetheros.memory.knowledge_graph")


@dataclass
class KGNode:
    """A node in the knowledge graph."""
    node_id: str = field(default_factory=lambda: f"kg-{uuid.uuid4().hex[:8]}")
    label: str = ""
    node_type: str = "entity"
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.node_id,
            "label": self.label,
            "type": self.node_type,
            "properties": self.properties,
        }


@dataclass
class KGEdge:
    """An edge in the knowledge graph."""
    edge_id: str = field(default_factory=lambda: f"kge-{uuid.uuid4().hex[:6]}")
    source_id: str = ""
    target_id: str = ""
    relation: str = ""
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.edge_id,
            "source": self.source_id,
            "target": self.target_id,
            "relation": self.relation,
            "weight": self.weight,
        }


class KnowledgeGraph:
    """Semantic knowledge graph for long-term reasoning."""

    def __init__(self):
        self._nodes: dict[str, KGNode] = {}
        self._edges: dict[str, KGEdge] = {}
        self._adjacency: dict[str, list[str]] = defaultdict(list)
        self._reverse_adjacency: dict[str, list[str]] = defaultdict(list)
        self._type_index: dict[str, set[str]] = defaultdict(set)

    def add_node(self, label: str, node_type: str = "entity",
                 properties: Optional[dict] = None, node_id: Optional[str] = None) -> str:
        node = KGNode(
            node_id=node_id or f"kg-{uuid.uuid4().hex[:8]}",
            label=label,
            node_type=node_type,
            properties=properties or {},
        )
        self._nodes[node.node_id] = node
        self._type_index[node_type].add(node.node_id)
        return node.node_id

    def add_edge(self, source_id: str, target_id: str, relation: str,
                 weight: float = 1.0, properties: Optional[dict] = None) -> Optional[str]:
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        edge = KGEdge(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=weight,
            properties=properties or {},
        )
        self._edges[edge.edge_id] = edge
        self._adjacency[source_id].append(edge.edge_id)
        self._reverse_adjacency[target_id].append(edge.edge_id)
        return edge.edge_id

    def get_node(self, node_id: str) -> Optional[dict]:
        node = self._nodes.get(node_id)
        return node.to_dict() if node else None

    def get_neighbors(self, node_id: str, relation: Optional[str] = None) -> list[dict]:
        results = []
        for edge_id in self._adjacency.get(node_id, []):
            edge = self._edges[edge_id]
            if relation and edge.relation != relation:
                continue
            target = self._nodes.get(edge.target_id)
            if target:
                results.append({
                    "node": target.to_dict(),
                    "relation": edge.relation,
                    "weight": edge.weight,
                })
        return results

    def query_by_type(self, node_type: str) -> list[dict]:
        return [self._nodes[nid].to_dict() for nid in self._type_index.get(node_type, set())]

    def shortest_path(self, start_id: str, end_id: str, max_depth: int = 10) -> list[str]:
        """BFS shortest path."""
        if start_id not in self._nodes or end_id not in self._nodes:
            return []
        visited = {start_id}
        queue = [(start_id, [start_id])]
        while queue:
            current, path = queue.pop(0)
            if current == end_id:
                return path
            if len(path) >= max_depth:
                continue
            for edge_id in self._adjacency.get(current, []):
                edge = self._edges[edge_id]
                if edge.target_id not in visited:
                    visited.add(edge.target_id)
                    queue.append((edge.target_id, path + [edge.target_id]))
        return []

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        node = self._nodes.pop(node_id)
        self._type_index[node.node_type].discard(node_id)
        edges_to_remove = (
            self._adjacency.pop(node_id, []) +
            self._reverse_adjacency.pop(node_id, [])
        )
        for eid in edges_to_remove:
            self._edges.pop(eid, None)
        return True

    def get_stats(self) -> dict:
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "node_types": {k: len(v) for k, v in self._type_index.items()},
        }

    def export_json(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges.values()],
        }
