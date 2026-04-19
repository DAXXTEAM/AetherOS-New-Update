"""Security policy engine for AetherOS."""
from __future__ import annotations

import fnmatch
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

logger = logging.getLogger("aetheros.security.policy")


class PolicyAction(Enum):
    ALLOW = auto()
    DENY = auto()
    WARN = auto()
    REQUIRE_APPROVAL = auto()


class ResourceType(Enum):
    FILE = "file"
    DIRECTORY = "directory"
    COMMAND = "command"
    NETWORK = "network"
    SYSTEM = "system"


@dataclass
class PolicyRule:
    """A single security policy rule."""
    rule_id: str
    resource_type: ResourceType
    pattern: str
    action: PolicyAction
    description: str = ""
    priority: int = 0
    conditions: dict[str, Any] = field(default_factory=dict)

    def matches(self, resource: str, context: Optional[dict] = None) -> bool:
        """Check if this rule matches the given resource."""
        try:
            if fnmatch.fnmatch(resource, self.pattern):
                return True
            if re.match(self.pattern, resource):
                return True
        except re.error:
            return fnmatch.fnmatch(resource, self.pattern)
        return False


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""
    action: PolicyAction
    rule_id: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        return self.action in (PolicyAction.ALLOW, PolicyAction.WARN)


class PolicyEngine:
    """Evaluates security policies against requested operations."""

    def __init__(self):
        self._rules: list[PolicyRule] = []
        self._load_default_rules()

    def _load_default_rules(self) -> None:
        """Load built-in security rules."""
        defaults = [
            # File access rules
            PolicyRule("F001", ResourceType.FILE, "/etc/shadow", PolicyAction.DENY,
                       "Block access to shadow file"),
            PolicyRule("F002", ResourceType.FILE, "/etc/passwd", PolicyAction.WARN,
                       "Warn on passwd access"),
            PolicyRule("F003", ResourceType.FILE, "*.key", PolicyAction.REQUIRE_APPROVAL,
                       "Require approval for key files"),
            PolicyRule("F004", ResourceType.FILE, "*.pem", PolicyAction.REQUIRE_APPROVAL,
                       "Require approval for certificate files"),
            PolicyRule("F005", ResourceType.DIRECTORY, "/", PolicyAction.DENY,
                       "Block root directory operations", priority=10),
            PolicyRule("F006", ResourceType.FILE, "/tmp/*", PolicyAction.ALLOW,
                       "Allow temp directory access", priority=5),

            # Command rules
            PolicyRule("C001", ResourceType.COMMAND, "rm -rf *", PolicyAction.DENY,
                       "Block recursive force delete"),
            PolicyRule("C002", ResourceType.COMMAND, "chmod 777 *", PolicyAction.DENY,
                       "Block world-writable permissions"),
            PolicyRule("C003", ResourceType.COMMAND, "sudo *", PolicyAction.REQUIRE_APPROVAL,
                       "Require approval for sudo"),
            PolicyRule("C004", ResourceType.COMMAND, r"curl .+\|.+", PolicyAction.DENY,
                       "Block piped curl commands"),

            # Network rules
            PolicyRule("N001", ResourceType.NETWORK, "*.internal", PolicyAction.DENY,
                       "Block internal network access"),
            PolicyRule("N002", ResourceType.NETWORK, "http://*", PolicyAction.WARN,
                       "Warn on non-HTTPS connections"),
        ]
        self._rules.extend(defaults)

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        return len(self._rules) < before

    def evaluate(self, resource_type: ResourceType, resource: str,
                 context: Optional[dict] = None) -> PolicyDecision:
        """Evaluate all matching policies for a resource."""
        matching = [
            r for r in self._rules
            if r.resource_type == resource_type and r.matches(resource, context)
        ]

        if not matching:
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                reason="No matching policy rules (default allow)",
            )

        # Highest priority rule wins; if tie, most restrictive wins
        priority_order = {
            PolicyAction.DENY: 4,
            PolicyAction.REQUIRE_APPROVAL: 3,
            PolicyAction.WARN: 2,
            PolicyAction.ALLOW: 1,
        }
        matching.sort(key=lambda r: (r.priority, priority_order.get(r.action, 0)), reverse=True)
        winner = matching[0]

        return PolicyDecision(
            action=winner.action,
            rule_id=winner.rule_id,
            reason=winner.description,
            details={"matched_rules": len(matching), "winning_rule": winner.rule_id},
        )

    def evaluate_command(self, command: str) -> PolicyDecision:
        return self.evaluate(ResourceType.COMMAND, command)

    def evaluate_file_access(self, path: str) -> PolicyDecision:
        return self.evaluate(ResourceType.FILE, path)

    def evaluate_network(self, url: str) -> PolicyDecision:
        return self.evaluate(ResourceType.NETWORK, url)

    def list_rules(self) -> list[dict]:
        return [
            {
                "id": r.rule_id,
                "type": r.resource_type.value,
                "pattern": r.pattern,
                "action": r.action.name,
                "description": r.description,
                "priority": r.priority,
            }
            for r in self._rules
        ]

    def get_stats(self) -> dict:
        by_type = {}
        by_action = {}
        for r in self._rules:
            by_type[r.resource_type.value] = by_type.get(r.resource_type.value, 0) + 1
            by_action[r.action.name] = by_action.get(r.action.name, 0) + 1
        return {"total_rules": len(self._rules), "by_type": by_type, "by_action": by_action}
