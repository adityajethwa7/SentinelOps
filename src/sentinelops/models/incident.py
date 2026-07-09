"""Incident, Hypothesis, and Plan data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Hypothesis:
    """A possible root-cause hypothesis produced by the Investigation agent."""

    id: Optional[int] = None
    incident_id: Optional[int] = None
    cause: str = ""  # e.g. "OOMKilled due to memory limit 128Mi"
    p_diagnosis: float = 0.0  # probability this is the right diagnosis
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """A remediation plan produced by the Planning agent."""

    id: Optional[int] = None
    incident_id: Optional[int] = None
    action: str = ""  # playbook action name, e.g. "increase_memory_limit"
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # combined confidence score
    blast_radius: str = "low"  # "low" | "medium" | "high"
    gate_decision: str = "pending"  # "auto_approved" | "human_approved" | "denied" | "pending" | "timeout_safe_default"
    dry_run_diff: str = ""  # human-readable diff from dry run


@dataclass
class Incident:
    """A full incident record in the database."""

    id: Optional[int] = None
    fingerprint: str = ""
    resource: str = ""
    namespace: str = ""
    symptom_tags: List[str] = field(default_factory=list)
    severity: str = "medium"
    raw_context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "open"  # "open" | "triaged" | "investigating" | "planned" | "executing" | "resolved" | "escalated" | "suppressed"
    hypotheses: List[Hypothesis] = field(default_factory=list)
    plans: List[Plan] = field(default_factory=list)
    provider: str = "mock"
    cluster_name: str = ""
