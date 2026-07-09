"""FixRecord — Beta-Binomial state per (action, symptom_cluster) pair."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple


@dataclass
class FixOutcome:
    """A single fix attempt outcome — appended to fix_outcomes table."""

    id: Optional[int] = None
    fix_record_id: Optional[int] = None
    success: bool = False
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FixRecord:
    """Tracks the Beta-Binomial state for one (action, symptom_cluster) pair.

    prior_a and prior_b are the accumulated (decayed) alpha/beta params.
    Outcomes are stored separately for decay recalculation.
    """

    id: Optional[int] = None
    action: str = ""  # playbook action name
    symptom_cluster: str = ""  # fingerprint or symptom tag cluster
    prior_a: float = 2.0  # Beta prior alpha
    prior_b: float = 2.0  # Beta prior beta
    outcomes: List[FixOutcome] = field(default_factory=list)

    def outcome_tuples(self) -> List[Tuple[bool, float]]:
        """Convert outcomes to (success, days_ago) tuples for confidence calc."""
        now = datetime.now(timezone.utc)
        result = []
        for o in self.outcomes:
            days_ago = (now - o.occurred_at).total_seconds() / 86400.0
            result.append((o.success, days_ago))
        return result
