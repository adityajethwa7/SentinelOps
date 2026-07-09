import pytest

def test_single_incident_lifecycle(client):
    """Test a full single incident lifecycle with manual gate approval (Tier 2)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    # 1. Ingest alert signal
    payload = {
        "resource": "pod/test-service",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp = client.post("/api/signals", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    incident_id = data["incident_id"]
    assert data["status"] == "pending"  # cold start goes to pending
    
    # 2. Check incident listed in feed
    feed_resp = client.get("/api/incidents")
    assert feed_resp.status_code == 200
    incidents = feed_resp.json()
    my_inc = next((i for i in incidents if i["id"] == incident_id), None)
    assert my_inc is not None
    assert my_inc["status"] == "pending"
    assert len(my_inc["plans"]) == 1
    
    # 3. Approve the plan
    plan_id = my_inc["plans"][0]["id"]
    approve_resp = client.post(f"/api/plans/{plan_id}/approve", headers=headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json() == {"status": "approved and executed"}
    
    # 4. Check incident is now resolved
    feed_resp = client.get("/api/incidents")
    incidents = feed_resp.json()
    my_inc = next((i for i in incidents if i["id"] == incident_id), None)
    assert my_inc["status"] == "resolved"

def test_single_incident_deny_path(client):
    """Test incident flow where manual gate denies the plan (Tier 2)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    # 1. Ingest new signal
    payload = {
        "resource": "pod/another-service",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp = client.post("/api/signals", json=payload, headers=headers)
    assert resp.status_code == 200
    incident_id = resp.json()["incident_id"]
    
    # 2. Find and deny the plan
    feed_resp = client.get("/api/incidents")
    my_inc = next((i for i in feed_resp.json() if i["id"] == incident_id), None)
    plan_id = my_inc["plans"][0]["id"]
    
    deny_resp = client.post(f"/api/plans/{plan_id}/deny", headers=headers)
    assert deny_resp.status_code == 200
    assert deny_resp.json() == {"status": "denied"}
    
    # 3. Verify status remains open
    feed_resp = client.get("/api/incidents")
    my_inc = next((i for i in feed_resp.json() if i["id"] == incident_id), None)
    assert my_inc["status"] == "open"
