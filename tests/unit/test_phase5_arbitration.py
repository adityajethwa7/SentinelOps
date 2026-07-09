"""Phase 5 — Arbitration tests.

Verifies automated gating logic for the Arbitration Agent.
"""

import pytest

from sentinelops.agents.arbitration import ArbitrationAgent
from sentinelops.models.incident import Hypothesis, Incident, Plan


@pytest.fixture
def agent():
    return ArbitrationAgent(confidence_threshold=0.85)


def test_auto_approve_high_confidence_low_blast(agent):
    """Should auto-approve if confidence >= threshold and blast is low."""
    incident = Incident(resource="pod/test", namespace="default")
    hyp = Hypothesis(cause="OOM", p_diagnosis=0.9)
    plan = Plan(
        incident_id=1, 
        action="restart_pod", 
        params={"namespace": "default"}, 
        confidence=0.90, 
        blast_radius="low"
    )
    
    assert agent.evaluate(incident, hyp, plan) == "approved"


def test_deny_denylisted_namespace(agent, monkeypatch):
    """Should auto-deny if namespace is in denylist."""
    from sentinelops.config.settings import settings
    monkeypatch.setattr(settings, "DENYLIST_NAMESPACES", "kube-system,default")
    
    incident = Incident(resource="pod/test", namespace="default")
    hyp = Hypothesis(cause="OOM", p_diagnosis=0.9)
    # Even with high confidence and low blast radius
    plan = Plan(
        incident_id=1, 
        action="restart_pod", 
        params={"namespace": "default"}, 
        confidence=0.99, 
        blast_radius="low"
    )
    
    assert agent.evaluate(incident, hyp, plan) == "denied"


def test_human_high_blast_radius(agent):
    """Should escalate to human if blast radius is high, regardless of confidence."""
    incident = Incident(resource="deploy/test", namespace="default")
    hyp = Hypothesis(cause="OOM", p_diagnosis=0.99)
    plan = Plan(
        incident_id=1, 
        action="scale_deployment", 
        params={"namespace": "default"}, 
        confidence=0.99, 
        blast_radius="high"
    )
    
    assert agent.evaluate(incident, hyp, plan) == "pending_human"


def test_human_low_confidence(agent):
    """Should escalate to human if confidence is below threshold."""
    incident = Incident(resource="pod/test", namespace="default")
    hyp = Hypothesis(cause="OOM", p_diagnosis=0.9)
    plan = Plan(
        incident_id=1, 
        action="restart_pod", 
        params={"namespace": "default"}, 
        confidence=0.80, # Below 0.85 threshold
        blast_radius="low"
    )
    
    assert agent.evaluate(incident, hyp, plan) == "pending_human"


def test_format_summary(agent):
    """Summary contains key information."""
    incident = Incident(resource="pod/test", namespace="default", fingerprint="fp123", symptom_tags=["OOMKilled"])
    incident.id = 42
    hyp = Hypothesis(cause="Memory Leak", p_diagnosis=0.9)
    plan = Plan(
        incident_id=42, 
        action="restart_pod", 
        params={"namespace": "default"}, 
        confidence=0.80, 
        blast_radius="low"
    )
    
    summary = agent.format_summary(incident, hyp, plan)
    
    assert "fp123" in summary
    assert "Memory Leak" in summary
    assert "restart_pod" in summary
    assert "/approve 42" in summary
