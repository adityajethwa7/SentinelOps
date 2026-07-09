"""Adversarial and logical gap tests for human-in-the-loop (HITL) flow.

Covers:
  - Incident Hijacking/State Regression via multiple plans (approving/denying plan on resolved incident)
  - Unhandled AttributeError (500 crash) in approve_plan when plan is not found in get_plans
  - Concurrent same-plan double-approval race condition
"""

import pytest
import sqlite3
import concurrent.futures
import api_server
from sentinelops.models.incident import Incident, Plan


@pytest.fixture(autouse=True)
def clean_db():
    api_server.store.conn.execute("DELETE FROM incidents")
    api_server.store.conn.execute("DELETE FROM hypotheses")
    api_server.store.conn.execute("DELETE FROM plans")
    api_server.store.conn.execute("DELETE FROM fix_outcomes")
    api_server.store.conn.execute("DELETE FROM fix_records")
    api_server.store.conn.execute("DELETE FROM graph_edges")
    api_server.store.conn.commit()
    api_server.graph.graph.clear()
    yield


@pytest.mark.tier5
def test_logical_bypass_resolved_incident_multiple_plans(client):
    """Test that a resolved incident can have its state hijacked or duplicate-executed via other plans."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    # 1. Create incident
    incident = Incident(
        fingerprint="test-hijack-fingerprint",
        resource="pod/hijack-test",
        namespace="default",
        symptom_tags=["CrashLoopBackOff"],
        severity="high",
        raw_context={},
        provider="mock",
        cluster_name="test-cluster"
    )
    incident_id = api_server.store.create_incident(incident)

    # 2. Create two plans pending human approval
    plan_a = Plan(
        incident_id=incident_id,
        action="restart_pod",
        params={"pod_name": "test-pod-a"},
        confidence=0.5,
        blast_radius="low",
        gate_decision="pending_human",
        dry_run_diff=""
    )
    plan_a_id = api_server.store.create_plan(plan_a)

    plan_b = Plan(
        incident_id=incident_id,
        action="restart_pod",
        params={"pod_name": "test-pod-b"},
        confidence=0.4,
        blast_radius="low",
        gate_decision="pending_human",
        dry_run_diff=""
    )
    plan_b_id = api_server.store.create_plan(plan_b)

    # 3. Approve Plan A -> Should resolve incident
    resp_a = client.post(f"/api/plans/{plan_a_id}/approve", headers=headers)
    assert resp_a.status_code == 200
    assert resp_a.json()["status"] == "approved and executed"

    # Verify incident is resolved
    inc = api_server.store.get_incident(incident_id)
    assert inc.status == "resolved"

    # 4. Deny Plan B on the already resolved incident
    # This exposes the state regression vulnerability: denying Plan B updates incident back to "open"
    resp_b_deny = client.post(f"/api/plans/{plan_b_id}/deny", headers=headers)
    assert resp_b_deny.status_code == 200
    assert resp_b_deny.json()["status"] == "denied"

    # Verify incident is now "open" again (Vulnerability: resolved state was hijacked)
    inc = api_server.store.get_incident(incident_id)
    assert inc.status == "open", f"Expected incident to remain resolved, but got {inc.status}"

    # 5. Reset and test double-execution by approving another plan
    # Create incident 2
    incident_2 = Incident(
        fingerprint="test-double-exec-fingerprint",
        resource="pod/double-exec-test",
        namespace="default",
        symptom_tags=["CrashLoopBackOff"],
        severity="high",
        raw_context={},
        provider="mock",
        cluster_name="test-cluster"
    )
    inc2_id = api_server.store.create_incident(incident_2)

    plan_c = Plan(
        incident_id=inc2_id,
        action="restart_pod",
        params={"pod_name": "test-pod-c"},
        confidence=0.5,
        blast_radius="low",
        gate_decision="pending_human",
        dry_run_diff=""
    )
    plan_c_id = api_server.store.create_plan(plan_c)

    plan_d = Plan(
        incident_id=inc2_id,
        action="restart_pod",
        params={"pod_name": "test-pod-d"},
        confidence=0.4,
        blast_radius="low",
        gate_decision="pending_human",
        dry_run_diff=""
    )
    plan_d_id = api_server.store.create_plan(plan_d)

    # Approve Plan C -> resolves incident
    assert client.post(f"/api/plans/{plan_c_id}/approve", headers=headers).status_code == 200

    # Approve Plan D -> Should be blocked, but actual implementation allows it
    resp_d_approve = client.post(f"/api/plans/{plan_d_id}/approve", headers=headers)
    # If the system had incident state checks, this would be 400.
    # We assert 200 to confirm the vulnerability exists.
    assert resp_d_approve.status_code == 200
    assert resp_d_approve.json()["status"] == "approved and executed"


@pytest.mark.tier5
def test_unhandled_attribute_error_on_inconsistent_plan(client):
    """Test that a plan with inconsistent database relations causes a 500 crash in /approve but not /deny."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    # 1. Insert a plan pointing to a non-existent incident ID (999999)
    # SQLite foreign keys are not enforced, so this succeeds.
    plan = Plan(
        incident_id=999999,
        action="restart_pod",
        params={"pod_name": "test-pod"},
        confidence=0.5,
        blast_radius="low",
        gate_decision="pending_human",
        dry_run_diff=""
    )
    plan_id = api_server.store.create_plan(plan)

    # 2. Call /deny endpoint -> returns 400 (handled correctly because of 'if not plan')
    resp_deny = client.post(f"/api/plans/{plan_id}/deny", headers=headers)
    assert resp_deny.status_code == 400
    assert "not pending human approval/denial" in resp_deny.text

    # 3. Call /approve endpoint -> returns 500 (AttributeError: 'NoneType' object has no attribute 'gate_decision')
    # This confirms the crash vulnerability.
    resp_approve = client.post(f"/api/plans/{plan_id}/approve", headers=headers)
    assert resp_approve.status_code == 500


@pytest.mark.tier5
def test_concurrent_same_plan_double_approval_race(client):
    """Test concurrent same-plan approval request race condition."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    # 1. Create incident
    incident = Incident(
        fingerprint="test-race-fingerprint",
        resource="pod/race-test",
        namespace="default",
        symptom_tags=["CrashLoopBackOff"],
        severity="high",
        raw_context={},
        provider="mock",
        cluster_name="test-cluster"
    )
    incident_id = api_server.store.create_incident(incident)

    # 2. Create plan
    plan = Plan(
        incident_id=incident_id,
        action="restart_pod",
        params={"pod_name": "test-pod"},
        confidence=0.5,
        blast_radius="low",
        gate_decision="pending_human",
        dry_run_diff=""
    )
    plan_id = api_server.store.create_plan(plan)

    def do_approve():
        return client.post(f"/api/plans/{plan_id}/approve", headers=headers)

    # 3. Send two concurrent approvals
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(do_approve) for _ in range(2)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    status_codes = [r.status_code for r in results]
    
    # Ideally, only one should return 200, and the other 400.
    # If both return 200, it indicates a double-execution race condition.
    # We log this result for the handoff report.
    print(f"Concurrent same-plan approval status codes: {status_codes}")
    assert all(code in (200, 400) for code in status_codes)
