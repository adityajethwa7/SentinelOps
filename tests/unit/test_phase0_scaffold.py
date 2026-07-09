"""Phase 0 — Scaffold sanity tests.

Verifies that the package imports cleanly and basic models instantiate.
"""

import pytest


def test_package_imports():
    """The sentinelops package can be imported."""
    import sentinelops
    assert sentinelops.__version__ == "1.0.0"


def test_settings_load():
    """Settings load from env with defaults."""
    from sentinelops.config.settings import Settings
    s = Settings()
    assert s.CLOUD_PROVIDER in ("gcp", "aws", "azure", "alibaba", "mock")
    assert isinstance(s.denylist, list)
    assert "kube-system" in s.denylist


def test_signal_model():
    """IncidentSignal creates and computes fingerprint."""
    from sentinelops.models.signal import IncidentSignal
    sig = IncidentSignal(
        resource="deployment/test",
        namespace="default",
        symptom_tags=["CrashLoopBackOff"],
        severity="high",
    )
    fp = sig.compute_fingerprint()
    assert len(fp) == 16
    assert fp == sig.fingerprint


def test_incident_model():
    """Incident model instantiates with defaults."""
    from sentinelops.models.incident import Incident, Hypothesis, Plan
    inc = Incident(resource="deploy/x", namespace="ns")
    assert inc.status == "open"
    h = Hypothesis(cause="OOM", p_diagnosis=0.8)
    assert h.p_diagnosis == 0.8
    p = Plan(action="restart", confidence=0.5)
    assert p.gate_decision == "pending"


def test_fix_record_model():
    """FixRecord instantiates with Beta priors."""
    from sentinelops.models.fix_record import FixRecord
    fr = FixRecord(action="restart_pod", symptom_cluster="abc")
    assert fr.prior_a == 2.0
    assert fr.prior_b == 2.0
