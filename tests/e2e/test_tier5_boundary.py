"""Boundary and edge-case tests (Tier 5).

Covers:
  - Approve/deny idempotency (already-approved / already-denied)
  - Approve/deny non-existent plan → 404
  - Empty database returns empty array
  - Incidents after all resolved
  - CSV ingestion edge cases (malformed, empty, invalid values, oversized)
  - Health endpoint under concurrent load
"""

import pytest
import concurrent.futures
import api_server


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
def test_approve_already_approved_plan(client):
    """Approving an already-approved plan returns 400 (not pending_human)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    resp = client.post("/api/signals", json={
        "resource": "pod/idempotent-approve",
        "namespace": "default",
        "raw_context": {},
    }, headers=headers)
    incident_id = resp.json()["incident_id"]

    feed = client.get("/api/incidents").json()
    incident = next(i for i in feed if i["id"] == incident_id)
    plan_id = incident["plans"][0]["id"]

    # First approve
    r1 = client.post(f"/api/plans/{plan_id}/approve", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["status"] == "approved and executed"

    # Second approve on same plan should fail
    r2 = client.post(f"/api/plans/{plan_id}/approve", headers=headers)
    assert r2.status_code == 400
    assert "not pending human" in r2.text.lower()


@pytest.mark.tier5
def test_deny_already_denied_plan(client):
    """Denying an already-denied plan returns 400."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    resp = client.post("/api/signals", json={
        "resource": "pod/idempotent-deny",
        "namespace": "default",
        "raw_context": {},
    }, headers=headers)
    incident_id = resp.json()["incident_id"]

    feed = client.get("/api/incidents").json()
    incident = next(i for i in feed if i["id"] == incident_id)
    plan_id = incident["plans"][0]["id"]

    r1 = client.post(f"/api/plans/{plan_id}/deny", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["status"] == "denied"
    
    r2 = client.post(f"/api/plans/{plan_id}/deny", headers=headers)
    assert r2.status_code == 400


@pytest.mark.tier5
def test_approve_nonexistent_plan(client):
    """Approving a non-existent plan ID returns 404."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    resp = client.post("/api/plans/999999/approve", headers=headers)
    assert resp.status_code == 404


@pytest.mark.tier5
def test_deny_nonexistent_plan(client):
    """Denying a non-existent plan ID returns 404."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    resp = client.post("/api/plans/999999/deny", headers=headers)
    assert resp.status_code == 404


@pytest.mark.tier5
def test_get_incidents_empty_database(client):
    """GET /api/incidents returns an empty list when no incidents exist."""
    resp = client.get("/api/incidents")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.tier5
def test_incidents_still_returned_after_resolved(client):
    """Resolved incidents still appear in the incidents feed."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    resp = client.post("/api/signals", json={
        "resource": "pod/resolve-check",
        "namespace": "default",
        "raw_context": {},
    }, headers=headers)
    incident_id = resp.json()["incident_id"]

    feed = client.get("/api/incidents").json()
    incident = next(i for i in feed if i["id"] == incident_id)
    plan_id = incident["plans"][0]["id"]
    client.post(f"/api/plans/{plan_id}/approve", headers=headers)

    # Resolved incident still in feed
    feed = client.get("/api/incidents").json()
    resolved = [i for i in feed if i["id"] == incident_id]
    assert len(resolved) == 1
    assert resolved[0]["status"] == "resolved"


@pytest.mark.tier5
def test_ingest_csv_missing_required_column(client):
    """CSV missing a required column (timestamp) returns 400."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    bad_csv = (
        "resource,symptom,action_taken,success\n"
        "pod/a,CrashLoopBackOff,restart_pod,1\n"
    )
    resp = client.post("/api/ingest", files={
        "file": ("bad.csv", bad_csv, "text/csv"),
    }, headers=headers)
    assert resp.status_code == 400


@pytest.mark.tier5
def test_ingest_csv_empty_file(client):
    """CSV with only a header row ingests 0 rows (returns 200)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    empty_csv = "resource,symptom,action_taken,success,timestamp\n"
    resp = client.post("/api/ingest", files={
        "file": ("empty.csv", empty_csv, "text/csv"),
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["rows_ingested"] == 0


@pytest.mark.tier5
def test_ingest_csv_invalid_success_value(client):
    """CSV with non-integer 'success' value returns 400."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    bad_csv = (
        "resource,symptom,action_taken,success,timestamp\n"
        "pod/a,CrashLoopBackOff,restart_pod,not_a_number,2026-07-09T00:00:00Z\n"
    )
    resp = client.post("/api/ingest", files={
        "file": ("bad.csv", bad_csv, "text/csv"),
    }, headers=headers)
    assert resp.status_code == 400


@pytest.mark.tier5
def test_ingest_csv_oversized_file(client):
    """CSV larger than 1 MB returns 413."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    header = "resource,symptom,action_taken,success,timestamp\n"
    row = "pod/a,CrashLoopBackOff,restart_pod,1,2026-01-01T00:00:00Z\n"
    # ~40 bytes per row × 30 000 rows ≈ 1.2 MB > 1 MB limit
    large_csv = header + row * 30000
    resp = client.post("/api/ingest", files={
        "file": ("large.csv", large_csv, "text/csv"),
    }, headers=headers)
    assert resp.status_code == 413


@pytest.mark.tier5
def test_health_endpoint_under_concurrent_load(client):
    """Health endpoint returns 200 for 50 concurrent requests."""
    def check_health(_):
        return client.get("/health")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(check_health, i) for i in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(r.status_code == 200 for r in results)
    assert all(
        r.json() == {"status": "ok", "service": "sentinelops"}
        for r in results
    )
