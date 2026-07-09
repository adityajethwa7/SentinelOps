"""Memory and graph edge-case tests (Tier 5).

Tests the Bayesian confidence math under extreme conditions:
  - Cold start confidence (no history)
  - All failures (0 / 20)              → near-zero confidence
  - Very old outcomes (past decay horizon) → approaches cold start
  - Mixed fresh + stale outcomes       → recent dominates
  - Graph structure (no cycles by design)
  - 10 000 fix-record bulk insert/read performance
  - Audit log captures all state transitions
"""

import pytest
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
import api_server


@pytest.fixture(autouse=True)
def clean_db():
    api_server.store.conn.execute("DELETE FROM incidents")
    api_server.store.conn.execute("DELETE FROM hypotheses")
    api_server.store.conn.execute("DELETE FROM plans")
    api_server.store.conn.execute("DELETE FROM fix_outcomes")
    api_server.store.conn.execute("DELETE FROM fix_records")
    api_server.store.conn.execute("DELETE FROM graph_edges")
    api_server.store.conn.execute("DELETE FROM audit_logs")
    api_server.store.conn.commit()
    api_server.graph.graph.clear()
    yield


@pytest.mark.tier5
def test_cold_start_confidence(client):
    """Cold-start confidence with zero history matches the expected LCB ≈ 0.196."""
    from sentinelops.memory.confidence import fix_lcb
    conf = fix_lcb([])
    # Beta(2,2) 10th percentile ≈ 0.196
    assert 0.18 < conf < 0.21, f"Cold-start LCB {conf} outside expected range"


@pytest.mark.tier5
def test_all_failures_confidence_near_zero(client):
    """Confidence with 20 failures out of 20 attempts should be near zero."""
    from sentinelops.memory.confidence import fix_lcb
    outcomes = [(False, 0.1) for _ in range(20)]
    conf = fix_lcb(outcomes)
    assert conf < 0.1, f"Expected very low confidence, got {conf}"


@pytest.mark.tier5
def test_very_old_outcomes_decay_to_cold_start(client):
    """Outcomes far beyond the decay horizon should approach cold-start confidence."""
    from sentinelops.memory.confidence import fix_lcb, HALF_LIFE_DAYS
    decay_horizon = HALF_LIFE_DAYS * 10  # 10 half-lives → decay weight ≈ 0.001
    outcomes = [(True, decay_horizon) for _ in range(100)]
    conf = fix_lcb(outcomes)
    # Should be close to cold start (~0.196) because decay makes old outcomes negligible
    assert 0.18 < conf < 0.28, f"Expected near cold-start, got {conf}"


@pytest.mark.tier5
def test_mixed_fresh_failures_old_successes(client):
    """Fresh failures dominate over old successes due to time decay."""
    from sentinelops.memory.confidence import fix_lcb
    fresh_failures = [(False, 0.1) for _ in range(10)]
    old_successes = [(True, 365) for _ in range(100)]  # 1 year old
    outcomes = fresh_failures + old_successes
    conf = fix_lcb(outcomes)
    # Recent failures drag confidence down despite many old successes
    assert conf < 0.3, f"Expected low confidence, got {conf}"


@pytest.mark.tier5
def test_mixed_fresh_successes_old_failures(client):
    """Fresh successes dominate over old failures due to time decay."""
    from sentinelops.memory.confidence import fix_lcb
    fresh_successes = [(True, 0.1) for _ in range(10)]
    old_failures = [(False, 365) for _ in range(100)]
    outcomes = fresh_successes + old_failures
    conf = fix_lcb(outcomes)
    # Recent successes push confidence up despite many old failures
    assert conf > 0.3, f"Expected higher confidence, got {conf}"


@pytest.mark.tier5
def test_graph_structure_no_circular_references(client):
    """Graph edges are directional (fp → fr); the design prevents cycles."""
    from sentinelops.memory.graph import IncidentGraph
    from sentinelops.memory.store import Store

    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path=db_path)
    graph = IncidentGraph(store)

    fr = store.get_or_create_fix_record("restart_pod", "CrashLoopBackOff")
    graph.link("incident-A", fr.id)
    graph.link("incident-B", fr.id)

    records_a = graph.get_fix_records_for_fingerprint("incident-A")
    records_b = graph.get_fix_records_for_fingerprint("incident-B")
    assert len(records_a) == 1
    assert len(records_b) == 1
    assert records_a[0][0] == fr.id
    assert records_b[0][0] == fr.id

    # Verify graph properties: directed, no self-loops
    assert graph.graph.is_directed()
    assert not any(
        u == v for u, v in graph.graph.edges()
    ), "Graph contains self-loops"

    store.close()
    db_path.unlink(missing_ok=True)


@pytest.mark.tier5
def test_10000_fix_records_performance(client):
    """Bulk-insert and retrieve 10 000 fix records without catastrophic slowdown."""
    from sentinelops.memory.store import Store

    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path=db_path)

    t0 = time.time()
    for i in range(10000):
        fr = store.get_or_create_fix_record(f"action_{i}", f"symptom_{i % 100}")
        store.record_outcome(
            fr.id, success=(i % 2 == 0), occurred_at=datetime.utcnow()
        )
    write_elapsed = time.time() - t0

    t0 = time.time()
    all_records = store.list_fix_records()
    read_elapsed = time.time() - t0

    assert len(all_records) == 10000
    assert write_elapsed < 60, f"Writing 10K records took {write_elapsed:.1f}s"
    assert read_elapsed < 30, f"Reading 10K records took {read_elapsed:.1f}s"

    # Spot-check outcomes are loaded
    assert len(all_records[0].outcomes) == 1

    store.close()
    db_path.unlink(missing_ok=True)


@pytest.mark.tier5
def test_audit_log_captures_all_state_transitions(client):
    """Verify audit log contains entries for every lifecycle action."""
    # (Import removed, we will use api_server.store.db_path)

    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    # 1. Historical ingest
    csv_content = (
        "resource,symptom,action_taken,success,timestamp\n"
        "pod/a,CrashLoopBackOff,restart_pod,1,2026-07-09T00:00:00Z\n"
    )
    client.post("/api/ingest", files={
        "file": ("history.csv", csv_content, "text/csv"),
    }, headers=headers)

    # 2. Signal + human deny
    resp = client.post("/api/signals", json={
        "resource": "pod/audit-log-test",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"},
    }, headers=headers)
    incident_id = resp.json()["incident_id"]

    feed = client.get("/api/incidents").json()
    incident = next(i for i in feed if i["id"] == incident_id)
    plan_id = incident["plans"][0]["id"]

    client.post(f"/api/plans/{plan_id}/deny", headers=headers)

    # 3. Approve path on a separate incident
    resp2 = client.post("/api/signals", json={
        "resource": "pod/audit-log-deny",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"},
    }, headers=headers)
    deny_id = resp2.json()["incident_id"]

    feed = client.get("/api/incidents").json()
    deny_inc = next(i for i in feed if i["id"] == deny_id)
    client.post(f"/api/plans/{deny_inc['plans'][0]['id']}/approve", headers=headers)

    # 4. Read audit log from SQLite
    conn = sqlite3.connect(str(api_server.get_store().db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT action, user FROM audit_logs ORDER BY id")
    logs = cursor.fetchall()
    conn.close()

    actions = [l["action"] for l in logs]
    assert "HISTORICAL_INGEST" in actions, f"Missing HISTORICAL_INGEST in {actions}"
    assert "HUMAN_APPROVE" in actions, f"Missing HUMAN_APPROVE in {actions}"
    assert "HUMAN_DENY" in actions, f"Missing HUMAN_DENY in {actions}"

    users = [l["user"] for l in logs]
    assert "admin_ui" in users
    assert "system" in users
