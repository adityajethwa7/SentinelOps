import pytest

def test_health_endpoint(client):
    """Test health check connectivity (Tier 1)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "sentinelops"}

def test_incidents_feed_connectivity(client):
    """Test retrieving incidents feed empty state (Tier 1)."""
    resp = client.get("/api/incidents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_signals_auth_gating(client):
    """Verify signals endpoint rejects unauthorized requests (Tier 1)."""
    resp = client.post("/api/signals", json={"resource": "pod/x", "namespace": "y", "raw_context": {}})
    assert resp.status_code == 401

def test_approve_auth_gating(client):
    """Verify approve endpoint rejects unauthorized requests (Tier 1)."""
    resp = client.post("/api/plans/1/approve")
    assert resp.status_code == 401

def test_ingest_auth_gating(client):
    """Verify ingest endpoint rejects unauthorized requests (Tier 1)."""
    resp = client.post("/api/ingest")
    assert resp.status_code == 401
