import pytest
import sqlite3
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

def test_human_flow_feature_coverage(client):
    """Tier 1: Feature coverage of the human flow (alert viewing, investigation, confidence, approval, denial)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    # 1. Ingest alert signal (resource = pod/human-flow-t1-approve)
    payload = {
        "resource": "pod/human-flow-t1-approve",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp = client.post("/api/signals", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    incident_id = data["incident_id"]
    assert data["status"] == "pending"  # Should go to pending (pending_human)

    # 2. Alert viewing: verify in feed
    feed_resp = client.get("/api/incidents")
    assert feed_resp.status_code == 200
    incidents = feed_resp.json()
    incident = next((i for i in incidents if i["id"] == incident_id), None)
    assert incident is not None
    assert incident["status"] == "pending"

    # 3. Investigation reviewing and Confidence evaluation: check nested plans
    assert len(incident["plans"]) == 1
    plan = incident["plans"][0]
    plan_id = plan["id"]
    assert plan["action"] == "restart_pod"
    assert plan["params"] == {"namespace": "default", "pod_name": "test-pod"}
    assert plan["gate_decision"] == "pending_human"
    # Evaluating confidence & blast radius
    assert plan["confidence"] > 0
    assert plan["blast_radius"] == "low"

    # 4. Approving plan
    approve_resp = client.post(f"/api/plans/{plan_id}/approve", headers=headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json() == {"status": "approved and executed"}

    # Verify status is now resolved
    feed_resp = client.get("/api/incidents")
    incident = next((i for i in feed_resp.json() if i["id"] == incident_id), None)
    assert incident["status"] == "resolved"
    assert incident["plans"][0]["gate_decision"] == "approved"

    # 5. Denying plan (ingest a separate signal)
    payload_deny = {
        "resource": "pod/human-flow-t1-deny",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp_deny = client.post("/api/signals", json=payload_deny, headers=headers)
    assert resp_deny.status_code == 200
    deny_incident_id = resp_deny.json()["incident_id"]

    feed_resp = client.get("/api/incidents")
    deny_incident = next((i for i in feed_resp.json() if i["id"] == deny_incident_id), None)
    deny_plan_id = deny_incident["plans"][0]["id"]

    deny_resp = client.post(f"/api/plans/{deny_plan_id}/deny", headers=headers)
    assert deny_resp.status_code == 200
    assert deny_resp.json() == {"status": "denied"}

    # Verify status is now open (denied)
    feed_resp = client.get("/api/incidents")
    deny_incident = next((i for i in feed_resp.json() if i["id"] == deny_incident_id), None)
    assert deny_incident["status"] == "open"
    assert deny_incident["plans"][0]["gate_decision"] == "denied"

def test_human_flow_boundaries(client):
    """Tier 2: Boundary/corner cases (invalid plan IDs, not pending_human plans, invalid API keys, duplicate operations)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    # Ingest signal
    payload = {
        "resource": "pod/human-flow-t2-boundary",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp = client.post("/api/signals", json=payload, headers=headers)
    assert resp.status_code == 200
    incident_id = resp.json()["incident_id"]

    feed_resp = client.get("/api/incidents")
    incident = next((i for i in feed_resp.json() if i["id"] == incident_id), None)
    plan_id = incident["plans"][0]["id"]

    # 1. Invalid plan IDs (404)
    assert client.post("/api/plans/999999/approve", headers=headers).status_code == 404
    assert client.post("/api/plans/999999/deny", headers=headers).status_code == 404

    # 2. Invalid API keys (401)
    bad_headers = {"X-API-Key": "wrong-key"}
    assert client.post(f"/api/plans/{plan_id}/approve", headers=bad_headers).status_code == 401
    assert client.post(f"/api/plans/{plan_id}/deny", headers=bad_headers).status_code == 401
    assert client.post(f"/api/plans/{plan_id}/approve").status_code == 401  # Missing key

    # 3. Duplicate operations (double approve, double deny, etc.)
    # Approve once
    assert client.post(f"/api/plans/{plan_id}/approve", headers=headers).status_code == 200
    # Try to approve again (400 - not pending human)
    assert client.post(f"/api/plans/{plan_id}/approve", headers=headers).status_code == 400

    # Test for denial flow duplication
    payload_deny = {
        "resource": "pod/human-flow-t2-boundary-deny",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp_deny = client.post("/api/signals", json=payload_deny, headers=headers)
    deny_incident_id = resp_deny.json()["incident_id"]
    feed_resp = client.get("/api/incidents")
    deny_incident = next((i for i in feed_resp.json() if i["id"] == deny_incident_id), None)
    deny_plan_id = deny_incident["plans"][0]["id"]

    # Deny once
    assert client.post(f"/api/plans/{deny_plan_id}/deny", headers=headers).status_code == 200
    # Try to deny again (400 - not pending human)
    assert client.post(f"/api/plans/{deny_plan_id}/deny", headers=headers).status_code == 400
    # Try to approve after denied (400 - not pending human)
    assert client.post(f"/api/plans/{deny_plan_id}/approve", headers=headers).status_code == 400

def test_human_flow_cross_feature(client):
    """Tier 3: Cross-feature interactions (timeout auto-denial, duplicate collapsing)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    # 1. Timeout auto-denial interacting with human gating
    payload_timeout = {
        "resource": "pod/human-flow-t3-timeout",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp = client.post("/api/signals", json=payload_timeout, headers=headers)
    incident_id = resp.json()["incident_id"]
    
    # Find plan
    feed_resp = client.get("/api/incidents")
    incident = next((i for i in feed_resp.json() if i["id"] == incident_id), None)
    plan_id = incident["plans"][0]["id"]
    
    # Trigger timeout check to auto-deny
    api_server.orch.check_timeouts()
    
    # Verify incident is open and plan is denied
    feed_resp = client.get("/api/incidents")
    incident = next((i for i in feed_resp.json() if i["id"] == incident_id), None)
    assert incident["status"] == "open"
    assert incident["plans"][0]["gate_decision"] == "denied"
    
    # Human try to approve the timed out plan (should fail with 400)
    assert client.post(f"/api/plans/{plan_id}/approve", headers=headers).status_code == 400
    # Human try to deny the timed out plan (should fail with 400)
    assert client.post(f"/api/plans/{plan_id}/deny", headers=headers).status_code == 400

    # 2. Duplicate signal collapsing: Ingest same signal while first is pending/open
    payload_dup = {
        "resource": "pod/human-flow-t3-dup",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    r1 = client.post("/api/signals", json=payload_dup, headers=headers)
    r2 = client.post("/api/signals", json=payload_dup, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["incident_id"] == r2.json()["incident_id"]

def test_human_flow_real_world_scenario(client):
    """Tier 4: Real-world application scenario: simulating a full operator shift."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    # Operator shift begins. Three distinct alerts are ingested
    services = ["web-app", "db-service", "auth-portal"]
    incident_ids = {}
    for s in services:
        resp = client.post("/api/signals", json={
            "resource": f"pod/{s}",
            "namespace": "default",
            "raw_context": {"alertname": "CrashLoopBackOff"}
        }, headers=headers)
        incident_ids[s] = resp.json()["incident_id"]
        assert resp.json()["status"] == "pending"

    # Ingest a denylisted namespace alert (should automatically deny / set status to open)
    resp_deny = client.post("/api/signals", json={
        "resource": "pod/critical-core",
        "namespace": "kube-system",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }, headers=headers)
    deny_id = resp_deny.json()["incident_id"]
    assert resp_deny.json()["status"] == "open"

    # Operator views incidents list (alert viewing)
    feed_resp = client.get("/api/incidents")
    incidents = feed_resp.json()

    # Operator reviews web-app investigation, evaluates confidence, and approves
    web_inc = next(i for i in incidents if i["id"] == incident_ids["web-app"])
    assert len(web_inc["plans"]) == 1
    web_plan = web_inc["plans"][0]
    assert web_plan["confidence"] > 0
    resp_app = client.post(f"/api/plans/{web_plan['id']}/approve", headers=headers)
    assert resp_app.status_code == 200

    # Operator reviews db-service and denies it due to low confidence / high risk
    db_inc = next(i for i in incidents if i["id"] == incident_ids["db-service"])
    db_plan = db_inc["plans"][0]
    resp_den = client.post(f"/api/plans/{db_plan['id']}/deny", headers=headers)
    assert resp_den.status_code == 200

    # auth-portal is left unattended. Operator shift changes, timeout runs
    api_server.orch.check_timeouts()

    # Verify final states of all incidents
    final_feed = client.get("/api/incidents").json()
    
    web_final = next(i for i in final_feed if i["id"] == incident_ids["web-app"])
    assert web_final["status"] == "resolved"
    assert web_final["plans"][0]["gate_decision"] == "approved"

    db_final = next(i for i in final_feed if i["id"] == incident_ids["db-service"])
    assert db_final["status"] == "open"
    assert db_final["plans"][0]["gate_decision"] == "denied"

    auth_final = next(i for i in final_feed if i["id"] == incident_ids["auth-portal"])
    assert auth_final["status"] == "open"
    assert auth_final["plans"][0]["gate_decision"] == "denied"  # timed out

    deny_final = next(i for i in final_feed if i["id"] == deny_id)
    assert deny_final["status"] == "open"

    # Verify audit logs in SQLite to ensure operator actions were logged correctly
    from sentinelops.memory.store import DEFAULT_DB_PATH
    conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT action, user FROM audit_logs ORDER BY id DESC")
    logs = cursor.fetchall()
    conn.close()
    
    actions = [l[0] for l in logs]
    # Check that HUMAN_APPROVE and HUMAN_DENY are present
    assert "HUMAN_APPROVE" in actions
    assert "HUMAN_DENY" in actions
