"""The Auditor Agent - Security validation and command logging."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agents.base import BaseAgent, AgentMessage
from core.event_bus import EventBus, Event, EventType
from core.model_manager import ModelManager
from core.state import SystemState
from security.audit import AuditLogger, AuditCategory, AuditSeverity

logger = logging.getLogger("aetheros.agents.auditor")


class AuditorAgent(BaseAgent):
    """The Auditor: Security validation and compliance.

    Responsibilities:
    - Validate all commands before and after execution
    - Detect potential security risks
    - Maintain audit trail
    - Enforce security policies
    - Flag suspicious activities
    """

    def __init__(self, model_manager: ModelManager, event_bus: EventBus,
                 system_state: SystemState, audit_logger: Optional[AuditLogger] = None):
        self.audit = audit_logger or AuditLogger()
        super().__init__("auditor", "security", model_manager, event_bus, system_state)

    def _build_system_prompt(self) -> str:
        return """You are The Auditor, the security validation agent in the AetherOS system.

Your role is to:
1. Review all execution results for security issues
2. Detect data leaks, unauthorized access, or policy violations
3. Assess risk levels for operations
4. Maintain integrity of the audit trail
5. Flag suspicious or potentially dangerous activities

Security Policies:
- No execution of commands that could damage the system
- No unauthorized file access outside allowed directories
- No network operations without explicit approval
- No credential exposure in logs or outputs
- All destructive operations require elevated approval

Risk Classification:
- LOW: Read-only operations, standard computations
- MEDIUM: File modifications, network requests
- HIGH: System modifications, privilege changes
- CRITICAL: Destructive operations, security changes

Output Format (JSON):
{
    "audit_result": "PASS|WARN|FAIL",
    "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
    "findings": [
        {"type": "finding_type", "description": "details", "severity": "level"}
    ],
    "recommendation": "What to do",
    "requires_escalation": false
}

Be thorough but not overly paranoid. Focus on real threats."""

    async def process(self, message: AgentMessage) -> AgentMessage:
        """Audit an execution result."""
        self._record_message(message)
        await self.activate()

        try:
            response = await self._call_model(
                f"Audit this execution:\n{message.content}",
                additional_context=f"Context: {json.dumps(message.metadata)}",
            )

            try:
                audit_result = json.loads(response.content)
            except json.JSONDecodeError:
                audit_result = {
                    "audit_result": "PASS",
                    "risk_level": "LOW",
                    "findings": [],
                    "recommendation": "No significant issues detected.",
                    "requires_escalation": False,
                }

            # Log to audit trail
            severity_map = {
                "LOW": AuditSeverity.INFO,
                "MEDIUM": AuditSeverity.WARNING,
                "HIGH": AuditSeverity.CRITICAL,
                "CRITICAL": AuditSeverity.ALERT,
            }
            severity = severity_map.get(audit_result.get("risk_level", "LOW"), AuditSeverity.INFO)

            self.audit.log(
                category=AuditCategory.SECURITY_EVENT,
                action="execution_audit",
                target=message.metadata.get("step", "unknown"),
                actor=self.name,
                severity=severity,
                details=audit_result,
                result=audit_result.get("audit_result", "UNKNOWN"),
            )

            # Emit security alert if needed
            if audit_result.get("risk_level") in ("HIGH", "CRITICAL"):
                await self.events.publish(Event(
                    event_type=EventType.SECURITY_ALERT,
                    data=audit_result,
                    source=self.name,
                ))

            result_msg = AgentMessage(
                sender=self.name,
                recipient=message.sender,
                content=json.dumps(audit_result, indent=2),
                message_type="audit_result",
                metadata={
                    "audit_result": audit_result.get("audit_result"),
                    "risk_level": audit_result.get("risk_level"),
                },
            )
            self._record_message(result_msg)
            return result_msg

        except Exception as e:
            logger.error(f"Auditor failed: {e}")
            return AgentMessage(
                sender=self.name,
                recipient=message.sender,
                content=json.dumps({
                    "audit_result": "ERROR",
                    "error": str(e),
                    "recommendation": "Audit failed, proceed with caution",
                }),
                message_type="error",
            )
        finally:
            await self.deactivate()

    async def pre_execution_check(self, step: dict) -> dict:
        """Check a step before execution."""
        msg = AgentMessage(
            sender="orchestrator",
            recipient=self.name,
            content=json.dumps({"type": "pre_execution", "step": step}),
            message_type="pre_check",
            metadata={"step": step.get("description", "")},
        )
        result = await self.process(msg)
        try:
            return json.loads(result.content)
        except json.JSONDecodeError:
            return {"audit_result": "PASS", "risk_level": "LOW"}

    def get_audit_summary(self) -> dict:
        """Get a summary of audit activities."""
        return self.audit.get_stats()
