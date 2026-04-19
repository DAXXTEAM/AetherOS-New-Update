#!/usr/bin/env python3
"""AetherOS v2.0   Ultra-Advanced Autonomous AI Agent System.

Post-Quantum Agentic OS with multi-agent orchestration, self-evolution,
cyber-defense sentinel, distributed mesh networking, biometric command
approval, and neural chain-of-thought visualization.

Usage:
    python aetheros.py                    # Interactive CLI mode
    python aetheros.py --gui              # Launch GUI control panel
    python aetheros.py --task "..."       # Execute a single task
    python aetheros.py --headless         # Headless daemon mode
    python aetheros.py --status           # Show system status
    python aetheros.py --mesh             # Enable mesh networking
    python aetheros.py --evolve           # Run self-evolution cycle
    python aetheros.py --neural-map       # Export neural visualization
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import AetherConfig, ModelConfig, ModelProvider
from config.logging_config import setup_logging, get_logger, get_gui_handler
from config.constants import SYSTEM_NAME, SYSTEM_VERSION, SYSTEM_CODENAME

from core.event_bus import EventBus, Event, EventType
from core.model_manager import ModelManager
from core.orchestrator import Orchestrator
from core.state import SystemState
from core.task import Task, TaskPriority
from core.evolution import EvolutionEngine
from core.mesh import MeshNetwork, MeshTask, TaskDistributionStrategy
from core.quantum_engine import QuantumCircuit, BB84Protocol, QuantumRNG

from tools.base import ToolRegistry
from tools.file_ops import FileOps
from tools.shell_ops import ShellOps
from tools.vision_ops import VisionOps
from tools.web_ops import WebOps
from tools.crypto_ops import CryptoOps
from tools.monitor_ops import MonitorOps
from tools.data_ops import DataOps

from security.crypto import QuantumSafeCrypto
from security.kill_switch import KillSwitch
from security.audit import AuditLogger
from security.sentinel import CyberDefenseSentinel
from security.biometric import YoKiMoBiometricEngine

from memory.chroma_store import ChromaMemoryStore
from memory.context import ContextManager
from memory.preferences import PreferenceStore
from memory.knowledge_graph import KnowledgeGraph

from agents.architect import ArchitectAgent
from agents.executor import ExecutorAgent
from agents.auditor import AuditorAgent
from agents.researcher import ResearcherAgent
from agents.guardian import GuardianAgent
from agents.team import AgentTeam

from gui.neural_map import NeuralMapManager


logger = get_logger("boot")


BANNER = f"""
 
                                                                
               
              
               
              
               
            
                                                 
                                                 
                                                 
                                                 
                                                 
                                                  
                                                                
   {SYSTEM_NAME} v{SYSTEM_VERSION}   Codename: {SYSTEM_CODENAME:25s}    
   Ultra-Advanced Autonomous AI Agent System                    
   Post-Quantum | Self-Evolving | Mesh-Distributed              
                                                                
 
"""


class AetherOS:
    """Main AetherOS v2.0 system class   orchestrates all components."""

    def __init__(self, config: AetherConfig, enable_mesh: bool = False,
                 enable_sentinel: bool = True, enable_evolution: bool = True):
        self.config = config
        self.config.ensure_dirs()
        self._boot_time = datetime.now()

        # Core components
        self.event_bus = EventBus()
        self.system_state = SystemState()
        self.logger = setup_logging(
            config.log_dir,
            level=logging.DEBUG if config.debug else logging.INFO,
        )

        logger.info(f"Initializing {SYSTEM_NAME} v{SYSTEM_VERSION} (Ultra-Advanced)")

        # Model Manager
        self.model_manager = ModelManager(config.model)
        logger.info(f"Model: {self.model_manager.get_status()}")

        # Security Layer
        self.crypto = QuantumSafeCrypto()
        self.kill_switch = KillSwitch(enabled=config.security.enable_kill_switch)
        self.audit = AuditLogger(log_dir=config.log_dir)
        logger.info(f"Security: Crypto={self.crypto.get_status()['kem_algorithm']}, "
                     f"KillSwitch={self.kill_switch.status.name}")

        # Biometric Engine (YoKiMo)
        self.biometric = YoKiMoBiometricEngine()
        logger.info(f"Biometric: YoKiMo engine initialized")

        # Cyber-Defense Sentinel
        self.sentinel = None
        if enable_sentinel:
            self.sentinel = CyberDefenseSentinel(
                auto_block=True,
                audit_logger=self.audit,
            )
            self.sentinel.start()
            logger.info("Sentinel: Cyber-Defense active")

        # Memory Layer
        self.memory = ChromaMemoryStore(
            persist_dir=config.memory.persist_directory,
            collection_name=config.memory.collection_name,
        )
        self.context_manager = ContextManager()
        self.preferences = PreferenceStore(self.memory)
        self.knowledge_graph = KnowledgeGraph()
        logger.info(f"Memory: {self.memory.get_stats()}")

        # Neural Visualization
        self.neural_map = NeuralMapManager()

        # Tools
        self.tool_registry = ToolRegistry()
        self._register_tools()

        # Agents
        self.architect = ArchitectAgent(
            self.model_manager, self.event_bus, self.system_state
        )
        self.executor = ExecutorAgent(
            self.model_manager, self.event_bus, self.system_state, self.tool_registry
        )
        self.auditor = AuditorAgent(
            self.model_manager, self.event_bus, self.system_state, self.audit
        )
        self.researcher = ResearcherAgent(
            self.model_manager, self.event_bus, self.system_state
        )
        self.guardian = GuardianAgent(
            self.model_manager, self.event_bus, self.system_state
        )

        # Register agents in neural map
        for agent_name, agent_role in [
            ("architect", "planning"), ("executor", "execution"),
            ("auditor", "security"), ("researcher", "research"),
            ("guardian", "threat_response"),
        ]:
            self.neural_map.register_agent(agent_name, agent_role)

        # Agent Team
        self.team = AgentTeam("alpha", self.event_bus)
        self.team.add_agent(self.architect)
        self.team.add_agent(self.executor)
        self.team.add_agent(self.auditor)
        self.team.add_agent(self.researcher)
        self.team.add_agent(self.guardian)

        # Orchestrator
        self.orchestrator = Orchestrator(
            self.model_manager, self.event_bus, self.system_state, self.tool_registry
        )

        # Self-Evolution Engine
        self.evolution = None
        if enable_evolution:
            project_root = os.path.dirname(os.path.abspath(__file__))
            self.evolution = EvolutionEngine(
                project_root=project_root,
                log_dir=config.log_dir,
                auto_apply=False,
                safety_checks=True,
            )
            logger.info("Evolution: Self-refactoring engine initialized")

        # Mesh Network
        self.mesh = None
        if enable_mesh:
            self.mesh = MeshNetwork(strategy=TaskDistributionStrategy.CONSISTENT_HASH)
            self.mesh.start()
            logger.info(f"Mesh: P2P network active at {self.mesh.local_peer.address}")

        # Quantum Engine
        self.quantum_rng = QuantumRNG()

        # Wire everything
        self.kill_switch.register_callback(self._on_kill_switch)
        self.kill_switch.start_monitoring()
        self._setup_event_handlers()

        logger.info(f"  {SYSTEM_NAME} v{SYSTEM_VERSION} initialization complete   Ultra-Advanced mode")

    def _register_tools(self) -> None:
        self.tool_registry.register(FileOps(
            allowed_dirs=self.config.security.allowed_directories,
            sandbox=self.config.security.sandbox_mode,
        ))
        self.tool_registry.register(ShellOps(
            sandbox=self.config.security.sandbox_mode,
            whitelist_enabled=self.config.security.command_whitelist_enabled,
            working_dir=self.config.workspace_dir,
        ))
        self.tool_registry.register(VisionOps())
        self.tool_registry.register(WebOps())
        self.tool_registry.register(CryptoOps(self.crypto))
        self.tool_registry.register(MonitorOps())
        self.tool_registry.register(DataOps())
        logger.info(f"Tools: {[t['name'] for t in self.tool_registry.list_tools()]}")

    def _setup_event_handlers(self) -> None:
        async def on_security_alert(event: Event):
            logger.warning(f"  Security Alert: {event.data}")
            self.audit.log_security_event(
                f"Alert: {event.data.get('risk_level', 'UNKNOWN')}",
                details=event.data,
            )
            # Forward to guardian
            if self.guardian:
                self.neural_map.record_thought(
                    "guardian", "threat_analysis",
                    f"Analyzing: {event.data.get('category', 'unknown')}",
                )

        async def on_task_complete(event: Event):
            task_id = event.data.get("task_id", "unknown")
            logger.info(f"Task completed: {task_id}")
            self.neural_map.record_thought(
                "orchestrator", "task_complete", f"Task {task_id} finished",
            )

        async def on_agent_activated(event: Event):
            agent_name = event.data.get("agent", "")
            from gui.neural_map import NodeState
            self.neural_map.update_agent_state(agent_name, NodeState.ACTIVE)

        async def on_agent_deactivated(event: Event):
            agent_name = event.data.get("agent", "")
            from gui.neural_map import NodeState
            self.neural_map.update_agent_state(agent_name, NodeState.IDLE)

        self.event_bus.subscribe(EventType.SECURITY_ALERT, on_security_alert)
        self.event_bus.subscribe(EventType.TASK_COMPLETED, on_task_complete)
        self.event_bus.subscribe(EventType.AGENT_ACTIVATED, on_agent_activated)
        self.event_bus.subscribe(EventType.AGENT_DEACTIVATED, on_agent_deactivated)

    def _on_kill_switch(self, event) -> None:
        logger.critical("  KILL SWITCH ENGAGED - Halting all operations")
        self.system_state.engage_kill_switch()
        self.audit.log_security_event(
            "KILL_SWITCH_ENGAGED",
            details=event.to_dict() if hasattr(event, "to_dict") else {},
        )
        if self.sentinel:
            self.sentinel.stop()
        if self.mesh:
            self.mesh.stop()

    async def execute_task(self, objective: str, context: str = "",
                           priority: TaskPriority = TaskPriority.NORMAL) -> dict:
        if self.kill_switch.is_engaged:
            return {"error": "Kill switch is engaged, operations halted"}

        task = Task(objective=objective, context=context, priority=priority)
        self.kill_switch.heartbeat()

        logger.info(f"  New task: {task.task_id}   {objective[:80]}")
        self.audit.log_command(f"task:{objective[:100]}", actor="user")

        # Register in neural map
        self.neural_map.register_task(task.task_id, objective)
        self.neural_map.record_thought("orchestrator", "task_received", objective[:100])

        # Distribute via mesh if available
        if self.mesh and self.mesh._running:
            mesh_task = MeshTask(task_id=task.task_id, objective=objective)
            assigned_peer = self.mesh.distribute_task(mesh_task)
            if assigned_peer != self.mesh.local_peer.peer_id:
                return {
                    "task_id": task.task_id,
                    "distributed_to": assigned_peer,
                    "status": "distributed",
                }

        result = await self.orchestrator.run_task(task)

        # Store in memory
        self.memory.store_text(
            f"Task: {objective}\nResult: {result.output[:500]}",
            category="task_history",
            tags=["task", "result"],
            importance=0.6,
        )

        return {
            "task_id": result.task_id,
            "success": result.success,
            "output": result.output,
            "metrics": result.metrics,
            "audit_trail": result.audit_trail,
        }

    async def run_evolution_cycle(self) -> dict:
        """Run a self-evolution cycle."""
        if not self.evolution:
            return {"error": "Evolution engine not enabled"}
        self.neural_map.record_thought("evolution", "cycle_start", "Scanning for failures")
        cycle = await self.evolution.run_cycle()
        self.neural_map.record_thought(
            "evolution", "cycle_complete", cycle.summary, duration_ms=0
        )
        return cycle.to_dict()

    def get_system_status(self) -> dict:
        status = {
            "system": {
                "name": SYSTEM_NAME,
                "version": SYSTEM_VERSION,
                "codename": SYSTEM_CODENAME,
                "boot_time": self._boot_time.isoformat(),
                "uptime_seconds": (datetime.now() - self._boot_time).total_seconds(),
            },
            "state": self.system_state.to_dict(),
            "model": self.model_manager.get_status(),
            "security": {
                "crypto": self.crypto.get_status(),
                "kill_switch": self.kill_switch.get_status(),
                "audit": self.audit.get_stats(),
                "biometric": self.biometric.get_stats(),
            },
            "memory": self.memory.get_stats(),
            "knowledge_graph": self.knowledge_graph.get_stats(),
            "tools": self.tool_registry.list_tools(),
            "agents": {
                "architect": self.architect.get_status(),
                "executor": self.executor.get_status(),
                "auditor": self.auditor.get_status(),
                "researcher": self.researcher.get_status(),
                "guardian": self.guardian.get_status(),
            },
            "team": self.team.get_status(),
            "neural_map": self.neural_map.get_stats(),
        }
        if self.sentinel:
            status["sentinel"] = self.sentinel.get_status()
        if self.evolution:
            status["evolution"] = self.evolution.get_status()
        if self.mesh:
            status["mesh"] = self.mesh.get_status()
        return status

    async def run_interactive(self) -> None:
        print(BANNER)
        print(f"Mode: {'Simulated' if self.model_manager.is_simulated else 'Live'} | "
              f"Model: {self.config.model.provider.value}/{self.config.model.model_name}")
        components = []
        if self.sentinel:
            components.append("Sentinel")
        if self.evolution:
            components.append("Evolution")
        if self.mesh:
            components.append("Mesh")
        print(f"Active: {', '.join(components) or 'Core only'}")
        print(f"Type 'help' for commands, 'quit' to exit\n")

        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("AetherOS> ").strip()
                )
            except (EOFError, KeyboardInterrupt):
                print("\nShutting down...")
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("Shutting down AetherOS...")
                break
            elif user_input.lower() == "help":
                self._print_help()
            elif user_input.lower() == "status":
                status = self.get_system_status()
                print(json.dumps(status, indent=2, default=str))
            elif user_input.lower() == "evolve":
                print("  Running self-evolution cycle...")
                result = await self.run_evolution_cycle()
                print(json.dumps(result, indent=2, default=str))
            elif user_input.lower() == "sentinel":
                if self.sentinel:
                    scan = self.sentinel.scan_now()
                    print(json.dumps(scan, indent=2, default=str))
                else:
                    print("Sentinel not enabled")
            elif user_input.lower() == "mesh":
                if self.mesh:
                    print(json.dumps(self.mesh.get_status(), indent=2, default=str))
                else:
                    print("Mesh not enabled")
            elif user_input.lower() == "neural":
                path = self.neural_map.export_html()
                print(f"Neural map exported to: {path}")
            elif user_input.lower() == "kill":
                self.kill_switch.engage("cli", "User initiated from CLI")
                print("  Kill switch engaged!")
            elif user_input.lower() == "unkill":
                self.kill_switch.disengage("cli-auth")
                print("Kill switch disengaged, entering cooldown")
            elif user_input.lower() == "tools":
                for t in self.tool_registry.list_tools():
                    print(f"    {t['name']}: {t['description']} (runs: {t['stats']['executions']})")
            elif user_input.lower() == "audit":
                entries = self.audit.get_entries(last_n=20)
                for e in entries:
                    print(f"  [{e['timestamp']}] [{e['severity']}] {e['action']}   {e['target'][:60]}")
            elif user_input.lower().startswith("remember "):
                text = user_input[9:]
                mid = self.memory.store_text(text, category="user_note", importance=0.8)
                print(f"Stored memory: {mid}")
            elif user_input.lower().startswith("recall "):
                query = user_input[7:]
                results = self.memory.search(query, n_results=5)
                for r in results:
                    print(f"  [{r['similarity']:.2f}] {r['content'][:100]}")
                if not results:
                    print("  No memories found.")
            elif user_input.lower().startswith("model "):
                parts = user_input.split()
                if len(parts) >= 2:
                    try:
                        p = ModelProvider(parts[1])
                        self.model_manager.switch_provider(p)
                        print(f"Switched to {parts[1]}")
                    except ValueError:
                        print(f"Unknown provider: {parts[1]}")
            else:
                print(f"\n  Executing: {user_input[:80]}...")
                result = await self.execute_task(user_input)
                print(f"\n{' ' if result.get('success') else ' '} Result:")
                print(result.get("output", result.get("error", "No output")))
                if result.get("metrics"):
                    print(f"\n  Metrics: {json.dumps(result['metrics'], indent=2)}")
                print()

        self.shutdown()

    def _print_help(self) -> None:
        print("""
AetherOS v2.0 Ultra-Advanced Commands:
  <task>        Execute a natural language task
  status        Show comprehensive system status
  tools         List available tools
  audit         Show recent audit entries
  evolve        Run self-evolution cycle
  sentinel      Run sentinel network scan
  mesh          Show mesh network status
  neural        Export neural map visualization
  model <name>  Switch model provider (openai/anthropic/google/ollama)
  remember <x>  Store a memory
  recall <x>    Search memories
  kill          Engage kill switch
  unkill        Disengage kill switch
  help          Show this help
  quit          Exit AetherOS
        """)

    def shutdown(self) -> None:
        logger.info("Shutting down AetherOS...")
        self.kill_switch.stop_monitoring()
        if self.sentinel:
            self.sentinel.stop()
        if self.mesh:
            self.mesh.stop()
        self.audit.log(
            category=__import__('security.audit', fromlist=['AuditCategory']).AuditCategory.SYSTEM_EVENT,
            action="system_shutdown",
            actor="system",
        )
        logger.info(f"AetherOS shutdown complete. Session: "
                     f"{(datetime.now() - self._boot_time).total_seconds():.1f}s")

    def launch_gui(self) -> None:
        try:
            from PyQt6.QtWidgets import QApplication
            from gui.control_panel import ControlPanel

            app = QApplication(sys.argv)
            panel = ControlPanel(system_state=self.system_state)

            gui_handler = get_gui_handler()
            gui_handler.register_callback(
                lambda entry: panel._terminal.log_received.emit(entry)
            )
            panel.task_submitted.connect(
                lambda task: asyncio.ensure_future(self.execute_task(task))
            )
            panel.kill_switch_triggered.connect(
                lambda: self.kill_switch.engage("gui", "GUI kill switch button")
            )
            panel.show()
            logger.info("GUI Control Panel launched")
            sys.exit(app.exec())
        except ImportError:
            logger.error("PyQt6 not installed. Running in CLI mode instead.")
            asyncio.run(self.run_interactive())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"{SYSTEM_NAME} v{SYSTEM_VERSION}   Ultra-Advanced Autonomous AI Agent System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--gui", action="store_true", help="Launch GUI control panel")
    parser.add_argument("--task", type=str, help="Execute a single task and exit")
    parser.add_argument("--headless", action="store_true", help="Headless daemon mode")
    parser.add_argument("--status", action="store_true", help="Show system status and exit")
    parser.add_argument("--mesh", action="store_true", help="Enable P2P mesh networking")
    parser.add_argument("--evolve", action="store_true", help="Run self-evolution cycle and exit")
    parser.add_argument("--neural-map", type=str, help="Export neural map to HTML file")
    parser.add_argument("--sentinel-scan", action="store_true", help="Run sentinel scan and exit")
    parser.add_argument("--provider", type=str, default="openai",
                        choices=["openai", "anthropic", "google", "ollama"],
                        help="LLM provider")
    parser.add_argument("--model", type=str, help="Model name override")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-sandbox", action="store_true", help="Disable sandbox mode")
    parser.add_argument("--no-kill-switch", action="store_true", help="Disable kill switch")
    parser.add_argument("--no-sentinel", action="store_true", help="Disable sentinel")
    parser.add_argument("--no-evolution", action="store_true", help="Disable evolution engine")
    return parser.parse_args()


def main():
    args = parse_args()

    config = AetherConfig(
        model=ModelConfig(
            provider=ModelProvider(args.provider),
            model_name=args.model,
        ),
        debug=args.debug,
    )
    config.security.sandbox_mode = not args.no_sandbox
    config.security.enable_kill_switch = not args.no_kill_switch

    system = AetherOS(
        config,
        enable_mesh=args.mesh,
        enable_sentinel=not args.no_sentinel,
        enable_evolution=not args.no_evolution,
    )

    if args.status:
        print(json.dumps(system.get_system_status(), indent=2, default=str))
        system.shutdown()
        return

    if args.evolve:
        result = asyncio.run(system.run_evolution_cycle())
        print(json.dumps(result, indent=2, default=str))
        system.shutdown()
        return

    if args.sentinel_scan:
        if system.sentinel:
            scan = system.sentinel.scan_now()
            print(json.dumps(scan, indent=2, default=str))
        system.shutdown()
        return

    if args.neural_map:
        path = system.neural_map.export_html(args.neural_map)
        print(f"Neural map exported to: {path}")
        system.shutdown()
        return

    if args.task:
        result = asyncio.run(system.execute_task(args.task))
        print(json.dumps(result, indent=2, default=str))
        system.shutdown()
        return

    if args.gui:
        system.launch_gui()
        return

    asyncio.run(system.run_interactive())


if __name__ == "__main__":
    main()
