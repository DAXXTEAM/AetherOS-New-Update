"""Neural Visualization   Advanced 2D/3D visualization of the
'Neural Chain of Thought' showing task graphs and agent interactions.

Provides both a PyQt6 widget for the control panel and a standalone
HTML/Canvas renderer for headless/web-based visualization.

Features:
- Task dependency graph with real-time state
- Agent interaction flow visualization
- Chain-of-thought reasoning path
- Performance heatmaps
- Animated data flow between nodes
- Force-directed graph layout
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import logging
import math
import os
import random
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional

logger = logging.getLogger("aetheros.gui.neural_map")


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class NodeType(Enum):
    AGENT = "agent"
    TASK = "task"
    TOOL = "tool"
    DECISION = "decision"
    DATA = "data"
    EVENT = "event"
    MEMORY = "memory"


class EdgeType(Enum):
    DELEGATION = "delegation"
    DATA_FLOW = "data_flow"
    DEPENDENCY = "dependency"
    MESSAGE = "message"
    FEEDBACK = "feedback"
    AUDIT = "audit"


class NodeState(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"
    BLOCKED = "blocked"


@dataclass
class GraphNode:
    """A node in the neural chain of thought graph."""
    node_id: str = field(default_factory=lambda: f"n-{uuid.uuid4().hex[:6]}")
    label: str = ""
    node_type: NodeType = NodeType.TASK
    state: NodeState = NodeState.IDLE
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    radius: float = 20.0
    color: str = "#58a6ff"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    weight: float = 1.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.node_id,
            "label": self.label,
            "type": self.node_type.value,
            "state": self.state.value,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "z": round(self.z, 2),
            "radius": self.radius,
            "color": self.color,
            "metadata": self.metadata,
        }


@dataclass
class GraphEdge:
    """An edge connecting two nodes."""
    edge_id: str = field(default_factory=lambda: f"e-{uuid.uuid4().hex[:6]}")
    source_id: str = ""
    target_id: str = ""
    edge_type: EdgeType = EdgeType.DATA_FLOW
    weight: float = 1.0
    color: str = "#30363d"
    label: str = ""
    animated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.edge_id,
            "source": self.source_id,
            "target": self.target_id,
            "type": self.edge_type.value,
            "weight": self.weight,
            "color": self.color,
            "label": self.label,
            "animated": self.animated,
        }


@dataclass
class ThoughtStep:
    """A single step in the chain of thought."""
    step_id: str = field(default_factory=lambda: f"thought-{uuid.uuid4().hex[:6]}")
    agent: str = ""
    action: str = ""
    reasoning: str = ""
    result: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    confidence: float = 0.0
    node_id: str = ""

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "agent": self.agent,
            "action": self.action,
            "reasoning": self.reasoning[:200],
            "result": self.result[:200],
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# Color Schemes
# ---------------------------------------------------------------------------

class NeuralColorScheme:
    """Color scheme for neural map visualization."""

    NODE_COLORS = {
        NodeType.AGENT: "#58a6ff",
        NodeType.TASK: "#3fb950",
        NodeType.TOOL: "#d29922",
        NodeType.DECISION: "#bc8cff",
        NodeType.DATA: "#79c0ff",
        NodeType.EVENT: "#f85149",
        NodeType.MEMORY: "#56d364",
    }

    STATE_COLORS = {
        NodeState.IDLE: "#8b949e",
        NodeState.ACTIVE: "#58a6ff",
        NodeState.COMPLETED: "#3fb950",
        NodeState.FAILED: "#f85149",
        NodeState.WAITING: "#d29922",
        NodeState.BLOCKED: "#ff6b6b",
    }

    EDGE_COLORS = {
        EdgeType.DELEGATION: "#58a6ff",
        EdgeType.DATA_FLOW: "#3fb950",
        EdgeType.DEPENDENCY: "#8b949e",
        EdgeType.MESSAGE: "#79c0ff",
        EdgeType.FEEDBACK: "#d29922",
        EdgeType.AUDIT: "#f85149",
    }

    @classmethod
    def get_node_color(cls, node: GraphNode) -> str:
        return cls.STATE_COLORS.get(node.state, cls.NODE_COLORS.get(node.node_type, "#8b949e"))

    @classmethod
    def get_edge_color(cls, edge: GraphEdge) -> str:
        return cls.EDGE_COLORS.get(edge.edge_type, "#30363d")

    @classmethod
    def generate_gradient(cls, color1: str, color2: str, steps: int) -> list[str]:
        """Generate a color gradient between two hex colors."""
        r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
        r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
        gradient = []
        for i in range(steps):
            t = i / max(steps - 1, 1)
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            gradient.append(f"#{r:02x}{g:02x}{b:02x}")
        return gradient


# ---------------------------------------------------------------------------
# Force-Directed Layout Engine
# ---------------------------------------------------------------------------

class ForceDirectedLayout:
    """Physics-based force-directed graph layout engine.

    Uses spring-electrical model:
    - Repulsive force between all nodes (Coulomb's law)
    - Attractive force along edges (Hooke's law)
    - Gravity pulling toward center
    - Damping to converge
    """

    def __init__(
        self,
        width: float = 800.0,
        height: float = 600.0,
        repulsion: float = 5000.0,
        attraction: float = 0.01,
        gravity: float = 0.1,
        damping: float = 0.85,
        min_distance: float = 30.0,
    ):
        self.width = width
        self.height = height
        self.repulsion = repulsion
        self.attraction = attraction
        self.gravity = gravity
        self.damping = damping
        self.min_distance = min_distance
        self._iterations = 0

    def initialize_positions(self, nodes: list[GraphNode]) -> None:
        """Assign initial random positions to nodes."""
        for node in nodes:
            if node.x == 0 and node.y == 0:
                node.x = random.uniform(50, self.width - 50)
                node.y = random.uniform(50, self.height - 50)

    def step(self, nodes: list[GraphNode], edges: list[GraphEdge]) -> float:
        """Perform one simulation step. Returns total kinetic energy."""
        if not nodes:
            return 0.0

        node_map = {n.node_id: n for n in nodes}
        total_energy = 0.0

        # Reset forces
        forces = {n.node_id: [0.0, 0.0] for n in nodes}

        # Repulsive forces between all node pairs
        for i, n1 in enumerate(nodes):
            for n2 in nodes[i + 1:]:
                dx = n1.x - n2.x
                dy = n1.y - n2.y
                dist = max(math.sqrt(dx * dx + dy * dy), self.min_distance)
                force = self.repulsion / (dist * dist)
                fx = (dx / dist) * force
                fy = (dy / dist) * force
                forces[n1.node_id][0] += fx
                forces[n1.node_id][1] += fy
                forces[n2.node_id][0] -= fx
                forces[n2.node_id][1] -= fy

        # Attractive forces along edges
        for edge in edges:
            n1 = node_map.get(edge.source_id)
            n2 = node_map.get(edge.target_id)
            if not n1 or not n2:
                continue
            dx = n2.x - n1.x
            dy = n2.y - n1.y
            dist = max(math.sqrt(dx * dx + dy * dy), 1.0)
            force = self.attraction * dist * edge.weight
            fx = (dx / dist) * force
            fy = (dy / dist) * force
            forces[n1.node_id][0] += fx
            forces[n1.node_id][1] += fy
            forces[n2.node_id][0] -= fx
            forces[n2.node_id][1] -= fy

        # Gravity toward center
        cx, cy = self.width / 2, self.height / 2
        for node in nodes:
            dx = cx - node.x
            dy = cy - node.y
            forces[node.node_id][0] += dx * self.gravity
            forces[node.node_id][1] += dy * self.gravity

        # Apply forces with damping
        for node in nodes:
            fx, fy = forces[node.node_id]
            node.velocity_x = (node.velocity_x + fx) * self.damping
            node.velocity_y = (node.velocity_y + fy) * self.damping
            node.x += node.velocity_x
            node.y += node.velocity_y

            # Boundary clamping
            node.x = max(node.radius, min(self.width - node.radius, node.x))
            node.y = max(node.radius, min(self.height - node.radius, node.y))

            total_energy += node.velocity_x ** 2 + node.velocity_y ** 2

        self._iterations += 1
        return total_energy

    def run(self, nodes: list[GraphNode], edges: list[GraphEdge],
            max_iterations: int = 300, energy_threshold: float = 0.01) -> int:
        """Run layout until convergence."""
        self.initialize_positions(nodes)
        for i in range(max_iterations):
            energy = self.step(nodes, edges)
            if energy < energy_threshold:
                return i + 1
        return max_iterations


# ---------------------------------------------------------------------------
# Neural Chain of Thought Graph
# ---------------------------------------------------------------------------

class NeuralChainGraph:
    """Manages the neural chain of thought graph."""

    def __init__(self, width: float = 800, height: float = 600):
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._thought_chain: list[ThoughtStep] = []
        self._layout = ForceDirectedLayout(width=width, height=height)
        self._event_log: deque[dict] = deque(maxlen=1000)
        self._snapshots: list[dict] = []

    def add_node(self, label: str, node_type: NodeType,
                 state: NodeState = NodeState.IDLE,
                 metadata: Optional[dict] = None,
                 node_id: Optional[str] = None) -> str:
        """Add a node to the graph."""
        node = GraphNode(
            node_id=node_id or f"n-{uuid.uuid4().hex[:6]}",
            label=label,
            node_type=node_type,
            state=state,
            color=NeuralColorScheme.NODE_COLORS.get(node_type, "#8b949e"),
            metadata=metadata or {},
        )
        # Scale radius by type
        type_sizes = {
            NodeType.AGENT: 30, NodeType.TASK: 22, NodeType.TOOL: 18,
            NodeType.DECISION: 16, NodeType.DATA: 14, NodeType.EVENT: 12,
            NodeType.MEMORY: 16,
        }
        node.radius = type_sizes.get(node_type, 18)
        self._nodes[node.node_id] = node
        self._log_event("node_added", {"node_id": node.node_id, "label": label})
        return node.node_id

    def add_edge(self, source_id: str, target_id: str,
                 edge_type: EdgeType = EdgeType.DATA_FLOW,
                 label: str = "", weight: float = 1.0,
                 animated: bool = False) -> Optional[str]:
        """Add an edge between two nodes."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            color=NeuralColorScheme.get_edge_color(GraphEdge(edge_type=edge_type)),
            label=label,
            animated=animated,
        )
        self._edges[edge.edge_id] = edge
        self._log_event("edge_added", {"edge_id": edge.edge_id, "source": source_id, "target": target_id})
        return edge.edge_id

    def update_node_state(self, node_id: str, state: NodeState) -> None:
        """Update a node's state."""
        if node_id in self._nodes:
            node = self._nodes[node_id]
            node.state = state
            node.color = NeuralColorScheme.get_node_color(node)
            node.updated_at = datetime.now()

    def record_thought(self, agent: str, action: str, reasoning: str,
                       result: str = "", duration_ms: float = 0,
                       confidence: float = 0.0) -> str:
        """Record a step in the chain of thought."""
        step = ThoughtStep(
            agent=agent,
            action=action,
            reasoning=reasoning,
            result=result,
            duration_ms=duration_ms,
            confidence=confidence,
        )
        self._thought_chain.append(step)

        # Create visualization node
        node_id = self.add_node(
            label=f"{agent}: {action[:30]}",
            node_type=NodeType.DECISION,
            state=NodeState.COMPLETED if result else NodeState.ACTIVE,
            metadata={"thought": step.to_dict()},
        )
        step.node_id = node_id

        # Connect to previous thought
        if len(self._thought_chain) > 1:
            prev = self._thought_chain[-2]
            if prev.node_id:
                self.add_edge(
                    prev.node_id, node_id,
                    edge_type=EdgeType.DATA_FLOW,
                    label=" ",
                    animated=True,
                )

        return step.step_id

    def layout(self, max_iterations: int = 200) -> int:
        """Run force-directed layout."""
        nodes = list(self._nodes.values())
        edges = list(self._edges.values())
        return self._layout.run(nodes, edges, max_iterations)

    def snapshot(self) -> dict:
        """Take a snapshot of the current graph state."""
        snap = {
            "timestamp": datetime.now().isoformat(),
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges.values()],
            "thought_chain": [t.to_dict() for t in self._thought_chain[-20:]],
            "stats": self.get_stats(),
        }
        self._snapshots.append(snap)
        if len(self._snapshots) > 100:
            self._snapshots = self._snapshots[-100:]
        return snap

    def get_stats(self) -> dict:
        type_counts = defaultdict(int)
        state_counts = defaultdict(int)
        for n in self._nodes.values():
            type_counts[n.node_type.value] += 1
            state_counts[n.state.value] += 1
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "thought_steps": len(self._thought_chain),
            "node_types": dict(type_counts),
            "node_states": dict(state_counts),
        }

    def to_json(self) -> str:
        return json.dumps(self.snapshot(), indent=2, default=str)

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        self._edges = {
            eid: e for eid, e in self._edges.items()
            if e.source_id != node_id and e.target_id != node_id
        }
        return True

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._thought_chain.clear()

    def _log_event(self, event_type: str, data: dict) -> None:
        self._event_log.append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        })


# ---------------------------------------------------------------------------
# HTML Canvas Renderer
# ---------------------------------------------------------------------------

class HTMLCanvasRenderer:
    """Generates standalone HTML with Canvas/SVG visualization."""

    @staticmethod
    def render(graph: NeuralChainGraph, title: str = "AetherOS Neural Map") -> str:
        """Render the graph as a standalone HTML page."""
        snapshot = graph.snapshot()
        nodes_json = json.dumps(snapshot["nodes"])
        edges_json = json.dumps(snapshot["edges"])
        thoughts_json = json.dumps(snapshot.get("thought_chain", []))

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0d1117; color: #e6edf3; font-family: 'Inter', system-ui, sans-serif; overflow: hidden; }}
#canvas {{ display: block; }}
#info {{ position: fixed; top: 10px; right: 10px; background: #161b22; border: 1px solid #30363d;
  border-radius: 8px; padding: 16px; min-width: 250px; max-height: 90vh; overflow-y: auto; font-size: 13px; }}
#info h3 {{ color: #58a6ff; margin-bottom: 8px; }}
.stat {{ color: #8b949e; margin: 4px 0; }}
.stat span {{ color: #e6edf3; float: right; }}
#thought-chain {{ position: fixed; bottom: 10px; left: 10px; right: 300px; background: #161b22;
  border: 1px solid #30363d; border-radius: 8px; padding: 12px; max-height: 200px; overflow-y: auto; }}
#thought-chain h4 {{ color: #3fb950; margin-bottom: 8px; }}
.thought {{ padding: 4px 8px; margin: 2px 0; border-left: 3px solid #58a6ff; font-size: 12px; }}
.legend {{ margin-top: 12px; }}
.legend-item {{ display: flex; align-items: center; margin: 3px 0; font-size: 12px; }}
.legend-dot {{ width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }}
</style>
</head>
<body>
<canvas id="canvas"></canvas>
<div id="info">
  <h3>  Neural Map</h3>
  <div class="stat">Nodes: <span id="node-count">0</span></div>
  <div class="stat">Edges: <span id="edge-count">0</span></div>
  <div class="stat">Thoughts: <span id="thought-count">0</span></div>
  <div class="stat">FPS: <span id="fps">0</span></div>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#58a6ff"></div>Agent</div>
    <div class="legend-item"><div class="legend-dot" style="background:#3fb950"></div>Task</div>
    <div class="legend-item"><div class="legend-dot" style="background:#d29922"></div>Tool</div>
    <div class="legend-item"><div class="legend-dot" style="background:#bc8cff"></div>Decision</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f85149"></div>Event</div>
  </div>
</div>
<div id="thought-chain">
  <h4>Chain of Thought</h4>
  <div id="thoughts"></div>
</div>
<script>
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
let nodes = {nodes_json};
let edges = {edges_json};
let thoughts = {thoughts_json};
let width, height, animFrame = 0, lastTime = 0, fps = 0;

function resize() {{
  width = canvas.width = window.innerWidth;
  height = canvas.height = window.innerHeight;
}}
window.addEventListener('resize', resize);
resize();

document.getElementById('node-count').textContent = nodes.length;
document.getElementById('edge-count').textContent = edges.length;
document.getElementById('thought-count').textContent = thoughts.length;

const thoughtsEl = document.getElementById('thoughts');
thoughts.forEach(t => {{
  const div = document.createElement('div');
  div.className = 'thought';
  div.innerHTML = `<b>${{t.agent}}</b>: ${{t.action}} <span style="color:#8b949e">(${{t.duration_ms?.toFixed(0) || 0}}ms)</span>`;
  thoughtsEl.appendChild(div);
}});

function drawEdge(edge) {{
  const src = nodes.find(n => n.id === edge.source);
  const tgt = nodes.find(n => n.id === edge.target);
  if (!src || !tgt) return;
  ctx.beginPath();
  ctx.moveTo(src.x, src.y);
  ctx.lineTo(tgt.x, tgt.y);
  ctx.strokeStyle = edge.color || '#30363d';
  ctx.lineWidth = edge.weight || 1;
  if (edge.animated) {{
    ctx.setLineDash([5, 5]);
    ctx.lineDashOffset = -animFrame * 0.5;
  }} else {{
    ctx.setLineDash([]);
  }}
  ctx.stroke();
  ctx.setLineDash([]);
  // Arrow
  const angle = Math.atan2(tgt.y - src.y, tgt.x - src.x);
  const r = tgt.radius || 20;
  const ax = tgt.x - Math.cos(angle) * r;
  const ay = tgt.y - Math.sin(angle) * r;
  ctx.beginPath();
  ctx.moveTo(ax, ay);
  ctx.lineTo(ax - 10*Math.cos(angle-0.3), ay - 10*Math.sin(angle-0.3));
  ctx.lineTo(ax - 10*Math.cos(angle+0.3), ay - 10*Math.sin(angle+0.3));
  ctx.closePath();
  ctx.fillStyle = edge.color || '#30363d';
  ctx.fill();
}}

function drawNode(node) {{
  const r = node.radius || 20;
  const pulse = node.state === 'active' ? Math.sin(animFrame * 0.05) * 5 : 0;
  // Glow
  if (node.state === 'active') {{
    const grad = ctx.createRadialGradient(node.x, node.y, r, node.x, node.y, r * 2 + pulse);
    grad.addColorStop(0, node.color + '40');
    grad.addColorStop(1, 'transparent');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r * 2 + pulse, 0, Math.PI * 2);
    ctx.fill();
  }}
  // Node
  ctx.beginPath();
  ctx.arc(node.x, node.y, r + pulse, 0, Math.PI * 2);
  ctx.fillStyle = node.color || '#58a6ff';
  ctx.fill();
  ctx.strokeStyle = '#e6edf3';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // Label
  ctx.fillStyle = '#e6edf3';
  ctx.font = '11px Inter, system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(node.label || '', node.x, node.y + r + 16);
}}

function draw(timestamp) {{
  if (lastTime) fps = Math.round(1000 / (timestamp - lastTime));
  lastTime = timestamp;
  if (animFrame % 30 === 0) document.getElementById('fps').textContent = fps;
  ctx.clearRect(0, 0, width, height);
  // Grid
  ctx.strokeStyle = '#21262d';
  ctx.lineWidth = 0.5;
  for (let x = 0; x < width; x += 40) {{ ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }}
  for (let y = 0; y < height; y += 40) {{ ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }}
  edges.forEach(drawEdge);
  nodes.forEach(drawNode);
  animFrame++;
  requestAnimationFrame(draw);
}}
requestAnimationFrame(draw);
</script>
</body>
</html>"""

    @staticmethod
    def save(graph: NeuralChainGraph, output_path: str,
             title: str = "AetherOS Neural Map") -> str:
        """Save the rendered HTML to a file."""
        html = HTMLCanvasRenderer.render(graph, title)
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)
        return output_path


# ---------------------------------------------------------------------------
# Neural Map Manager   Integration point for the system
# ---------------------------------------------------------------------------

class NeuralMapManager:
    """High-level manager for neural visualization across the system."""

    def __init__(self, output_dir: str = "/tmp/aetheros_neural"):
        self.graph = NeuralChainGraph()
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # Pre-create agent nodes
        self._agent_nodes: dict[str, str] = {}
        self._task_nodes: dict[str, str] = {}

    def register_agent(self, name: str, role: str) -> str:
        """Register an agent as a permanent node."""
        if name in self._agent_nodes:
            return self._agent_nodes[name]
        node_id = self.graph.add_node(
            label=f"{name} ({role})",
            node_type=NodeType.AGENT,
            state=NodeState.IDLE,
            metadata={"role": role},
        )
        self._agent_nodes[name] = node_id
        return node_id

    def register_task(self, task_id: str, description: str) -> str:
        """Register a task node."""
        node_id = self.graph.add_node(
            label=description[:40],
            node_type=NodeType.TASK,
            state=NodeState.WAITING,
            metadata={"task_id": task_id},
        )
        self._task_nodes[task_id] = node_id
        return node_id

    def record_agent_interaction(
        self, from_agent: str, to_agent: str,
        message_type: str, content_preview: str = ""
    ) -> Optional[str]:
        """Record an interaction between agents."""
        src = self._agent_nodes.get(from_agent)
        tgt = self._agent_nodes.get(to_agent)
        if not src or not tgt:
            return None
        edge_type_map = {
            "delegation": EdgeType.DELEGATION,
            "audit": EdgeType.AUDIT,
            "feedback": EdgeType.FEEDBACK,
            "message": EdgeType.MESSAGE,
        }
        return self.graph.add_edge(
            src, tgt,
            edge_type=edge_type_map.get(message_type, EdgeType.MESSAGE),
            label=content_preview[:20],
            animated=True,
        )

    def update_agent_state(self, name: str, state: NodeState) -> None:
        node_id = self._agent_nodes.get(name)
        if node_id:
            self.graph.update_node_state(node_id, state)

    def update_task_state(self, task_id: str, state: NodeState) -> None:
        node_id = self._task_nodes.get(task_id)
        if node_id:
            self.graph.update_node_state(node_id, state)

    def record_thought(self, agent: str, action: str, reasoning: str,
                       result: str = "", duration_ms: float = 0) -> str:
        return self.graph.record_thought(agent, action, reasoning, result, duration_ms)

    def export_html(self, filename: str = "neural_map.html") -> str:
        """Export visualization as HTML."""
        self.graph.layout()
        path = os.path.join(self.output_dir, filename)
        return HTMLCanvasRenderer.save(self.graph, path)

    def get_snapshot(self) -> dict:
        self.graph.layout(max_iterations=50)
        return self.graph.snapshot()

    def get_stats(self) -> dict:
        return {
            "agents_registered": len(self._agent_nodes),
            "tasks_registered": len(self._task_nodes),
            **self.graph.get_stats(),
        }
