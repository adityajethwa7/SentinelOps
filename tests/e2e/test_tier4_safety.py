import pytest
import api_server

def test_denylist_gating(client):
    """Verify that signals in denylisted namespaces are rejected/remain open (Tier 4)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    payload = {
        "resource": "pod/kube-apiserver",
        "namespace": "kube-system",  # Denylisted namespace
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp = client.post("/api/signals", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"  # Refused auto-remediation due to safety denylist

def test_duplicate_signal_collapsing(client):
    """Verify that concurrent or duplicate signals collapse into a single incident (Tier 4)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    payload = {
        "resource": "pod/redundant-worker",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    
    # Ingest twice
    r1 = client.post("/api/signals", json=payload, headers=headers)
    r2 = client.post("/api/signals", json=payload, headers=headers)
    
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["incident_id"] == r2.json()["incident_id"]

def test_approval_timeout_fallback(client):
    """Verify that pending approvals default to denied after running timeout checks (Tier 4)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    payload = {
        "resource": "pod/timeout-worker",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp = client.post("/api/signals", json=payload, headers=headers)
    incident_id = resp.json()["incident_id"]
    
    # Check that it starts as pending
    assert resp.json()["status"] == "pending"
    
    # Simulate the timeout job
    from sentinelops.api.server import orch
    orch.check_timeouts()
    
    # Verify it has defaulted to denied / open
    feed_resp = client.get("/api/incidents")
    my_inc = next((i for i in feed_resp.json() if i["id"] == incident_id), None)
    assert my_inc["status"] == "open"
    assert my_inc["plans"][0]["gate_decision"] == "denied"

def test_invalid_signal_validation(client):
    """Verify standard FastAPI validation holds for invalid inputs (Tier 4)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    # Missing resource
    resp = client.post("/api/signals", json={"namespace": "default", "raw_context": {}}, headers=headers)
    assert resp.status_code == 422
