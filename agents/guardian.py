"""Guardian Agent   Advanced threat response and system protection."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agents.base import BaseAgent, AgentMessage
from core.event_bus import EventBus, Event, EventType
from core.model_manager import ModelManager
from core.state import SystemState

logger = logging.getLogger("aetheros.agents.guardian")


class GuardianAgent(BaseAgent):
    """The Guardian: Advanced threat response and system protection.

    Responsibilities:
    - Monitor security events in real-time
    - Coordinate response to detected threats
    - Manage quarantine procedures
    - Interface with the Sentinel firewall
    - Provide threat intelligence analysis
    """

    def __init__(self, model_manager: ModelManager, event_bus: EventBus,
                 system_state: SystemState):
        super().__init__("guardian", "security_response", model_manager, event_bus, system_state)
        self._threat_log: list[dict] = []
        self._quarantine_list: list[dict] = []
        self._response_protocols: dict[str, dict] = {
            "port_scan": {"action": "block_source", "severity": "high", "auto_respond": True},
            "brute_force": {"action": "lockout", "severity": "critical", "auto_respond": True},
            "data_exfiltration": {"action": "isolate", "severity": "critical", "auto_respond": True},
            "malware": {"action": "quarantine", "severity": "critical", "auto_respond": True},
            "unauthorized_access": {"action": "block_and_alert", "severity": "high", "auto_respond": True},
            "suspicious_activity": {"action": "monitor", "severity": "medium", "auto_respond": False},
        }

    def _build_system_prompt(self) -> str:
        return """You are The Guardian, the advanced threat response agent in AetherOS.

Your role is to:
1. Analyze security events and classify threats
2. Determine appropriate response actions
3. Coordinate with other security components
4. Manage quarantine and isolation procedures
5. Provide real-time threat intelligence

Response Protocols:
- port_scan: Block source IP
- brute_force: Account lockout + IP block
- data_exfiltration: Network isolation
- malware: File quarantine + system scan
- unauthorized_access: Block + alert
- suspicious_activity: Enhanced monitoring

Output Format (JSON):
{
    "threat_classification": "type",
    "severity": "LOW|MEDIUM|HIGH|CRITICAL",
    "response_action": "action_to_take",
    "details": {},
    "requires_human_review": false,
    "recommended_actions": []
}"""

    async def process(self, message: AgentMessage) -> AgentMessage:
        self._record_message(message)
        await self.activate()
        try:
            response = await self._call_model(
                f"Analyze this security event and determine response:\n{message.content}"
            )
            try:
                result = json.loads(response.content)
            except json.JSONDecodeError:
                result = {
                    "threat_classification": "suspicious_activity",
                    "severity": "MEDIUM",
                    "response_action": "monitor",
                    "requires_human_review": True,
                }

            self._threat_log.append({
                "event": message.content[:200],
                "response": result,
                "timestamp": message.timestamp.isoformat(),
            })

            # Auto-respond if configured
            threat_type = result.get("threat_classification", "")
            protocol = self._response_protocols.get(threat_type)
            if protocol and protocol.get("auto_respond"):
                result["auto_response_applied"] = protocol["action"]

            return AgentMessage(
                sender=self.name,
                recipient=message.sender,
                content=json.dumps(result, indent=2),
                message_type="threat_response",
                metadata={"severity": result.get("severity", "UNKNOWN")},
            )
        except Exception as e:
            logger.error(f"Guardian failed: {e}")
            return AgentMessage(
                sender=self.name, recipient=message.sender,
                content=json.dumps({"error": str(e)}), message_type="error",
            )
        finally:
            await self.deactivate()

    def quarantine(self, item: dict) -> None:
        self._quarantine_list.append(item)

    def get_threat_summary(self) -> dict:
        return {
            "total_events": len(self._threat_log),
            "quarantined_items": len(self._quarantine_list),
            "active_protocols": len(self._response_protocols),
        }
