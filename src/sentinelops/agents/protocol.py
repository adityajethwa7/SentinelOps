"""Multi-agent communication protocol for SentinelOps.

Defines structured message types for agent-to-agent handoffs in the
SentinelOps pipeline. Each agent produces a typed output that the next
agent in the chain can consume, enabling:

1. Clear contract boundaries between agents
2. Structured logging of agent decisions
3. Future extensibility for parallel agent execution
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Enumeration of agent roles in the pipeline."""
    TRIAGE = "triage"
    INVESTIGATION = "investigation"
    PLANNING = "planning"
    ARBITRATION = "arbitration"
    EXECUTION = "execution"


@dataclass
class AgentMessage:
    """A structured message passed between agents in the pipeline.

    Each agent produces one message containing its output, which is then
    consumed by the next agent. This creates an auditable trail of
    agent-to-agent communication.
    """
    sender: AgentRole
    receiver: AgentRole
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    trace_id: Optional[str] = None  # For distributed tracing

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TriageOutput:
    """Structured output from the Triage Agent."""
    symptom_tags: List[str]
    severity: str
    reasoning: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TriageOutput":
        return cls(
            symptom_tags=data.get("symptom_tags", ["unknown"]),
            severity=data.get("severity", "high"),
            reasoning=data.get("reasoning", "No reasoning provided"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InvestigationOutput:
    """Structured output from the Investigation Agent."""
    cause: str
    p_diagnosis: float
    evidence: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvestigationOutput":
        return cls(
            cause=data.get("cause", "Unknown"),
            p_diagnosis=data.get("p_diagnosis", 0.0),
            evidence=data.get("evidence", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlanningOutput:
    """Structured output from the Planning Agent."""
    action: str
    params: Dict[str, Any]
    blast_radius: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanningOutput":
        return cls(
            action=data.get("action", "unknown"),
            params=data.get("params", {}),
            blast_radius=data.get("blast_radius", "high"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentPipeline:
    """Orchestrates the multi-agent communication pipeline.

    Tracks all messages exchanged between agents for a single incident,
    providing an audit trail and enabling future replay/analysis.
    """

    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        self.messages: List[AgentMessage] = []

    def record(self, sender: AgentRole, receiver: AgentRole, payload: Dict[str, Any]):
        """Record an agent-to-agent message."""
        msg = AgentMessage(
            sender=sender,
            receiver=receiver,
            payload=payload,
            trace_id=self.trace_id,
        )
        self.messages.append(msg)
        logger.debug(
            f"[{self.trace_id}] {sender.value} → {receiver.value}: "
            f"{list(payload.keys())}"
        )

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Return the full audit trail as a list of dicts."""
        return [m.to_dict() for m in self.messages]

    @property
    def step_count(self) -> int:
        return len(self.messages)
