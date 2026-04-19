"""Tests for Neural Visualization."""
import json
import os
import tempfile
import pytest
from gui.neural_map import (
    NeuralChainGraph, NeuralMapManager, HTMLCanvasRenderer,
    ForceDirectedLayout, GraphNode, GraphEdge, NodeType, NodeState,
    EdgeType, NeuralColorScheme, ThoughtStep,
)


class TestForceDirectedLayout:
    def test_initialize_positions(self):
        layout = ForceDirectedLayout(width=400, height=300)
        nodes = [GraphNode(label="A"), GraphNode(label="B")]
        layout.initialize_positions(nodes)
        assert nodes[0].x != 0 or nodes[0].y != 0
        assert nodes[1].x != 0 or nodes[1].y != 0

    def test_step(self):
        layout = ForceDirectedLayout()
        nodes = [GraphNode(label="A", x=100, y=100), GraphNode(label="B", x=500, y=500)]
        edges = [GraphEdge(source_id=nodes[0].node_id, target_id=nodes[1].node_id)]
        energy = layout.step(nodes, edges)
        assert energy >= 0

    def test_run_converges(self):
        layout = ForceDirectedLayout(width=200, height=200)
        nodes = [GraphNode(label=f"N{i}") for i in range(3)]
        edges = [GraphEdge(source_id=nodes[0].node_id, target_id=nodes[1].node_id)]
        iterations = layout.run(nodes, edges, max_iterations=50)
        assert iterations >= 1

    def test_empty_graph(self):
        layout = ForceDirectedLayout()
        energy = layout.step([], [])
        assert energy == 0.0


class TestNeuralChainGraph:
    def test_add_node(self):
        graph = NeuralChainGraph()
        nid = graph.add_node("Test Node", NodeType.TASK)
        assert nid in graph._nodes
        assert graph._nodes[nid].label == "Test Node"

    def test_add_edge(self):
        graph = NeuralChainGraph()
        n1 = graph.add_node("A", NodeType.AGENT)
        n2 = graph.add_node("B", NodeType.TASK)
        eid = graph.add_edge(n1, n2, EdgeType.DELEGATION)
        assert eid is not None

    def test_edge_invalid_nodes(self):
        graph = NeuralChainGraph()
        eid = graph.add_edge("fake-1", "fake-2")
        assert eid is None

    def test_update_node_state(self):
        graph = NeuralChainGraph()
        nid = graph.add_node("Test", NodeType.TASK)
        graph.update_node_state(nid, NodeState.ACTIVE)
        assert graph._nodes[nid].state == NodeState.ACTIVE

    def test_record_thought(self):
        graph = NeuralChainGraph()
        sid = graph.record_thought("architect", "plan", "Planning step")
        assert sid.startswith("thought-")
        assert len(graph._thought_chain) == 1

    def test_thought_chain_connected(self):
        graph = NeuralChainGraph()
        graph.record_thought("architect", "plan", "Step 1")
        graph.record_thought("executor", "execute", "Step 2")
        assert len(graph._edges) >= 1

    def test_snapshot(self):
        graph = NeuralChainGraph()
        graph.add_node("A", NodeType.AGENT)
        snap = graph.snapshot()
        assert "nodes" in snap
        assert "edges" in snap
        assert len(snap["nodes"]) == 1

    def test_to_json(self):
        graph = NeuralChainGraph()
        graph.add_node("Test", NodeType.TASK)
        j = graph.to_json()
        data = json.loads(j)
        assert len(data["nodes"]) == 1

    def test_remove_node(self):
        graph = NeuralChainGraph()
        nid = graph.add_node("Remove Me", NodeType.DATA)
        assert graph.remove_node(nid)
        assert nid not in graph._nodes

    def test_clear(self):
        graph = NeuralChainGraph()
        graph.add_node("A", NodeType.AGENT)
        graph.add_node("B", NodeType.TASK)
        graph.clear()
        assert len(graph._nodes) == 0

    def test_stats(self):
        graph = NeuralChainGraph()
        graph.add_node("A", NodeType.AGENT)
        graph.add_node("B", NodeType.TASK)
        stats = graph.get_stats()
        assert stats["total_nodes"] == 2


class TestHTMLCanvasRenderer:
    def test_render(self):
        graph = NeuralChainGraph()
        graph.add_node("Test", NodeType.AGENT)
        html = HTMLCanvasRenderer.render(graph)
        assert "<html" in html
        assert "canvas" in html

    def test_save(self):
        with tempfile.TemporaryDirectory() as d:
            graph = NeuralChainGraph()
            graph.add_node("Test", NodeType.AGENT, NodeState.ACTIVE)
            path = HTMLCanvasRenderer.save(graph, os.path.join(d, "test.html"))
            assert os.path.exists(path)
            with open(path) as f:
                content = f.read()
            assert "Test" in content


class TestNeuralMapManager:
    def test_register_agent(self):
        mgr = NeuralMapManager()
        nid = mgr.register_agent("architect", "planning")
        assert nid is not None
        assert "architect" in mgr._agent_nodes

    def test_register_task(self):
        mgr = NeuralMapManager()
        nid = mgr.register_task("task-1", "Test task")
        assert nid is not None

    def test_record_interaction(self):
        mgr = NeuralMapManager()
        mgr.register_agent("architect", "planning")
        mgr.register_agent("executor", "execution")
        eid = mgr.record_agent_interaction("architect", "executor", "delegation", "test")
        assert eid is not None

    def test_export_html(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = NeuralMapManager(output_dir=d)
            mgr.register_agent("test", "test")
            path = mgr.export_html()
            assert os.path.exists(path)

    def test_get_stats(self):
        mgr = NeuralMapManager()
        mgr.register_agent("a", "r")
        stats = mgr.get_stats()
        assert stats["agents_registered"] == 1


class TestColorScheme:
    def test_gradient(self):
        colors = NeuralColorScheme.generate_gradient("#000000", "#ffffff", 5)
        assert len(colors) == 5
        assert colors[0] == "#000000"
        assert colors[-1] == "#ffffff"
