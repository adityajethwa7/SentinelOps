"""Arbitration agent (Stage E).

Evaluates the proposed plan against safety rules, confidence thresholds,
and decides whether to auto-approve, auto-deny, or escalate to a human.
"""

from __future__ import annotations

from sentinelops.config.settings import settings
from sentinelops.models.incident import Hypothesis, Incident, Plan


class ArbitrationAgent:
    """Evaluates remediation plans for safety and confidence."""

    def __init__(self, confidence_threshold: float | None = None):
        self.confidence_threshold = confidence_threshold

    def evaluate(self, incident: Incident, hypothesis: Hypothesis, plan: Plan) -> str:
        """Evaluate the plan and return a gate decision.
        
        Returns one of: 'approved', 'denied', 'pending_human'
        """
        # 1. Hard deny for denylisted namespaces
        namespace = incident.namespace
        # Some plans might override or have their own namespace in params
        if "namespace" in plan.params:
            namespace = plan.params["namespace"]
            
        if incident.namespace in settings.denylist or namespace in settings.denylist:
            return "denied"

        # 2. Hard deny for high blast radius unless confidence is perfect
        # (Actually, let's always require human for high blast radius)
        if plan.blast_radius == "high":
            return "pending_human"

        # 3. Check confidence threshold
        threshold = self.confidence_threshold
        if threshold is None:
            threshold = settings.LOW_BLAST_BAR if plan.blast_radius == "low" else settings.PROD_AUTO_BAR

        if plan.confidence >= threshold:
            # High confidence, low/medium blast radius
            if plan.blast_radius == "medium":
                return "pending_human"  # Medium might still require a human depending on policy, let's say pending
            return "approved"  # Low blast, high confidence -> Auto approve

        # 4. Low confidence -> Escalate to human
        return "pending_human"

    def format_summary(self, incident: Incident, hypothesis: Hypothesis, plan: Plan) -> str:
        """Format a human-readable summary for Telegram."""
        return (
            f"🚨 **Incident {incident.fingerprint}**\n"
            f"**Resource:** {incident.resource} ({incident.namespace})\n"
            f"**Severity:** {incident.severity}\n"
            f"**Symptoms:** {', '.join(incident.symptom_tags)}\n\n"
            f"**Diagnosis:** {hypothesis.cause} (Confidence: {hypothesis.p_diagnosis:.2f})\n\n"
            f"**Proposed Action:** {plan.action}\n"
            f"**Params:** {plan.params}\n"
            f"**System Confidence in Fix:** {plan.confidence:.2f}\n"
            f"**Blast Radius:** {plan.blast_radius}\n\n"
            f"Please reply with `/approve {incident.id}` or `/deny {incident.id}`"
        )
