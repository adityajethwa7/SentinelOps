"""IncidentSignal — normalized alert from any cloud connector."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class IncidentSignal:
    """A normalized incident signal ingested from a cloud provider or K8s watch.

    This is the Stage A output — the raw signal that enters the pipeline.
    """

    resource: str  # e.g. "deployment/my-app"
    namespace: str  # e.g. "production"
    symptom_tags: List[str] = field(default_factory=list)  # e.g. ["CrashLoopBackOff", "OOMKilled"]
    severity: str = "unknown"  # "low" | "medium" | "high" | "critical"
    raw_context: Dict[str, Any] = field(default_factory=dict)
    provider: str = "mock"  # gcp|aws|azure|alibaba|mock
    cluster_name: str = ""
    fingerprint: str = ""  # computed hash of (resource, symptom_tags)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signal_id: Optional[str] = None

    @classmethod
    def from_raw(cls, raw: dict) -> "IncidentSignal":
        signal = cls(
            resource=raw.get("resource", "unknown"),
            namespace=raw.get("namespace", "default"),
            symptom_tags=raw.get("symptom_tags", []),
            severity=raw.get("severity", "unknown"),
            raw_context=raw,
            provider=raw.get("provider", "mock"),
            cluster_name=raw.get("cluster_name", "")
        )
        signal.compute_fingerprint()
        return signal

    def compute_fingerprint(self) -> str:
        """Generate a stable fingerprint from resource + sorted symptom tags."""
        import hashlib

        key = f"{self.resource}::{','.join(sorted(self.symptom_tags))}"
        self.fingerprint = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.fingerprint
