"""Phase 1 — Memory subsystem tests.

Verifies SQLite CRUD, NetworkX graph linking, and the critical confidence math.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest
from scipy.stats import beta

from sentinelops.memory.confidence import action_confidence, fix_lcb
from sentinelops.memory.graph import IncidentGraph
from sentinelops.memory.store import Store
from sentinelops.models.fix_record import FixRecord
from sentinelops.models.incident import Hypothesis, Incident, Plan


def test_confidence_cold_start():
    """With no history (0/0), the Beta(2,2) prior gives LCB ≈ 0.196."""
    lcb = fix_lcb([])
    # Beta(2,2) 10th percentile is ~0.1958
    assert math.isclose(lcb, 0.1958, abs_tol=0.001)

    # Combined confidence should scale linearly with p_diagnosis
    assert math.isclose(action_confidence(1.0, []), 0.1958, abs_tol=0.001)
    assert math.isclose(action_confidence(0.5, []), 0.0979, abs_tol=0.001)


def test_confidence_small_sample_punishment():
    """1/1 success should have LOWER confidence than 18/20 success.
    This proves the system punishes thin evidence (the naive bug)."""
    # 1 success, 0 days ago
    outcomes_1_1 = [(True, 0.0)]
    lcb_1_1 = fix_lcb(outcomes_1_1)

    # 18 successes, 2 failures, 0 days ago
    outcomes_18_20 = [(True, 0.0)] * 18 + [(False, 0.0)] * 2
    lcb_18_20 = fix_lcb(outcomes_18_20)

    # Naive math says 1.0 > 0.9. Our math correctly says 18/20 is safer.
    assert lcb_1_1 < lcb_18_20


def test_confidence_decay():
    """An old success should contribute less weight than a recent success."""
    outcomes_recent = [(True, 0.0)]
    outcomes_old = [(True, 90.0)]  # 1 half-life ago (should carry 50% weight)

    lcb_recent = fix_lcb(outcomes_recent)
    lcb_old = fix_lcb(outcomes_old)

    assert lcb_old < lcb_recent


@pytest.fixture
def store(tmp_path):
    """Provide an isolated, in-memory SQLite store."""
    db_path = tmp_path / "test.db"
    s = Store(db_path=db_path)
    yield s
    s.close()


def test_store_incident_crud(store: Store):
    """Test incident insertion and retrieval."""
    inc = Incident(
        fingerprint="fp123",
        resource="pod/test",
        namespace="default",
        symptom_tags=["OOMKilled"],
    )
    inc_id = store.create_incident(inc)
    assert inc_id > 0

    retrieved = store.get_incident(inc_id)
    assert retrieved.fingerprint == "fp123"
    assert retrieved.symptom_tags == ["OOMKilled"]
    assert retrieved.status == "open"

    store.update_incident_status(inc_id, "resolved")
    assert store.get_incident(inc_id).status == "resolved"


def test_store_fix_record_and_outcomes(store: Store):
    """Test FixRecord creation and outcome recording."""
    fr = store.get_or_create_fix_record("restart_pod", "OOMKilled")
    assert fr.id > 0
    assert len(fr.outcomes) == 0

    # Record some outcomes
    now = datetime.utcnow()
    store.record_outcome(fr.id, success=True, occurred_at=now)
    store.record_outcome(fr.id, success=False, occurred_at=now - timedelta(days=1))

    # Retrieve and verify
    fr_loaded = store.get_fix_record(fr.id)
    assert len(fr_loaded.outcomes) == 2
    assert fr_loaded.outcomes[0].success is False  # Order by occurred_at
    assert fr_loaded.outcomes[1].success is True

    # Test tuple conversion for confidence module
    tuples = fr_loaded.outcome_tuples()
    assert len(tuples) == 2
    # The older one should have a days_ago > 0
    assert tuples[0][0] is False
    assert tuples[0][1] >= 0.99
    assert tuples[1][0] is True


def test_incident_graph(store: Store):
    """Test graph edge persistence and querying."""
    graph = IncidentGraph(store=store)

    # Link a fingerprint to a fix record
    fr_id = 42
    graph.link("fpA", fr_id, weight=1.0)
    graph.link("fpA", fr_id, weight=1.0)  # Should increment weight to 2.0

    fr_list = graph.get_fix_records_for_fingerprint("fpA")
    assert len(fr_list) == 1
    assert fr_list[0] == (42, 2.0)

    # Re-instantiate graph to test loading from SQLite
    graph2 = IncidentGraph(store=store)
    fr_list2 = graph2.get_fix_records_for_fingerprint("fpA")
    assert len(fr_list2) == 1
    assert fr_list2[0] == (42, 2.0)
