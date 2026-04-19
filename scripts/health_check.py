#!/usr/bin/env python3
"""AetherOS Health Check Script."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import SYSTEM_NAME, SYSTEM_VERSION


def check_imports():
    """Check that all core modules can be imported."""
    modules = [
        "core.evolution", "core.mesh", "core.quantum_engine",
        "core.event_bus", "core.model_manager", "core.orchestrator",
        "core.state", "core.task", "core.pipeline", "core.scheduler",
        "security.crypto", "security.audit", "security.kill_switch",
        "security.policy", "security.sentinel", "security.biometric",
        "tools.base", "tools.file_ops", "tools.shell_ops",
        "tools.vision_ops", "tools.web_ops", "tools.crypto_ops",
        "tools.monitor_ops", "tools.data_ops",
        "agents.architect", "agents.executor", "agents.auditor",
        "agents.researcher", "agents.guardian", "agents.base", "agents.team",
        "memory.chroma_store", "memory.context", "memory.preferences",
        "memory.knowledge_graph",
        "gui.neural_map", "gui.theme",
        "protocols.wire", "protocols.consensus",
        "net.transport", "net.service_discovery",
        "config.settings", "config.constants", "config.logging_config",
    ]
    results = {}
    for mod in modules:
        try:
            __import__(mod)
            results[mod] = "OK"
        except Exception as e:
            results[mod] = f"FAIL: {e}"
    return results


def main():
    print(f"\n{SYSTEM_NAME} v{SYSTEM_VERSION}   Health Check\n{'='*50}")
    results = check_imports()
    ok = sum(1 for v in results.values() if v == "OK")
    fail = sum(1 for v in results.values() if v != "OK")
    for mod, status in sorted(results.items()):
        icon = " " if status == "OK" else " "
        print(f"  {icon} {mod}: {status}")
    print(f"\n{'='*50}")
    print(f"Total: {len(results)} | OK: {ok} | FAIL: {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
