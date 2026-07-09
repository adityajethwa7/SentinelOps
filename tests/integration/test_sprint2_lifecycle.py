import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import json

from sentinelops.api.server import app, get_store, get_graph, get_orch
from sentinelops.models.signal import IncidentSignal

client = TestClient(app)

def create_role_based_mock_client(blast_radius="low"):
    """Create a mock LLM client that returns different responses based on the calling agent."""
    mock_client = MagicMock()
    
    triage_args = json.dumps({
        "symptom_tags": ["OOMKilled"],
        "severity": "high",
        "reasoning": "OOM"
    })
    inv_args = json.dumps({
        "cause": "Memory Leak",
        "p_diagnosis": 1.0,
        "evidence": {}
    })
    plan_args = json.dumps({
        "action": "restart_pod",
        "params": {"namespace": "default", "pod_name": "api"},
        "blast_radius": blast_radius
    })

    def side_effect(*args, **kwargs):
        sys_prompt = kwargs["messages"][0]["content"]
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_tool = MagicMock()
        
        if "Triage" in sys_prompt:
            mock_tool.function.arguments = triage_args
        elif "Investigator" in sys_prompt:
            mock_tool.function.arguments = inv_args
        elif "Planner" in sys_prompt:
            mock_tool.function.arguments = plan_args
            
        mock_choice.message.tool_calls = [mock_tool]
        mock_resp.choices = [mock_choice]
        return mock_resp
        
    mock_client.chat.completions.create.side_effect = side_effect
    return mock_client

@pytest.fixture(autouse=True)
def setup_teardown():
    with TestClient(app) as client:
        from sentinelops.api import server
        
        # Default mock client returns low blast radius -> auto-approves if confidence is high
        mock_client = create_role_based_mock_client(blast_radius="low")
        server.get_orch().triage.client_override = mock_client
        server.get_orch().investigation.client_override = mock_client
        server.get_orch().planning.client_override = mock_client
        
        server.get_store().conn.execute("DELETE FROM incidents")
        server.get_store().conn.execute("DELETE FROM hypotheses")
        server.get_store().conn.execute("DELETE FROM plans")
        server.get_store().conn.execute("DELETE FROM fix_outcomes")
        server.get_store().conn.execute("DELETE FROM fix_records")
        server.get_store().conn.execute("DELETE FROM graph_edges")
        server.get_store().conn.commit()
        server.get_graph().graph.clear()
        
        yield client

def test_lifecycle_1_success(setup_teardown):
    c = setup_teardown
    from sentinelops.api import server
    
    # Seed DB so confidence is high
    fr = server.get_store().get_or_create_fix_record("restart_pod", "OOMKilled")
    for _ in range(10):
        server.get_store().record_outcome(fr.id, success=True)
        
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    payload = {"resource": "pod/test-1", "namespace": "default", "raw_context": {}}
    res = c.post("/api/signals", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"

def test_lifecycle_2_unauthorized(setup_teardown):
    c = setup_teardown
    payload = {"resource": "pod/test-2", "namespace": "default", "raw_context": {}}
    res = c.post("/api/signals", json=payload)
    assert res.status_code == 401

def test_lifecycle_3_invalid_apikey(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "wrong-key"}
    payload = {"resource": "pod/test-3", "namespace": "default", "raw_context": {}}
    res = c.post("/api/signals", json=payload, headers=headers)
    assert res.status_code == 401

def test_lifecycle_4_missing_resource(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    payload = {"namespace": "default", "raw_context": {}}
    res = c.post("/api/signals", json=payload, headers=headers)
    assert res.status_code == 422

def test_lifecycle_5_malformed_csv_negative(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    # Missing action_taken column
    csv_data = "resource,symptom,success,timestamp\npod/a,OOM,1,2026-07-09T00:00:00Z\n"
    res = c.post("/api/ingest", files={"file": ("data.csv", csv_data, "text/csv")}, headers=headers)
    assert res.status_code == 400
    assert "Missing required CSV column" in res.json()["detail"]

def test_lifecycle_6_oversized_payload_signal(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    large_context = {"data": "x" * 110000}
    payload = {"resource": "pod/large", "namespace": "default", "raw_context": large_context}
    res = c.post("/api/signals", json=payload, headers=headers)
    assert res.status_code == 413

def test_lifecycle_7_oversized_csv_negative(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    large_csv = "resource,symptom,action_taken,success,timestamp\n" + "pod/a,OOM,restart,1,2026-07-09T00:00:00Z\n" * 25000
    res = c.post("/api/ingest", files={"file": ("large.csv", large_csv, "text/csv")}, headers=headers)
    assert res.status_code == 413

def test_lifecycle_8_concurrent_duplicates(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    payload = {"resource": "pod/duplicate", "namespace": "default", "raw_context": {}}
    
    res1 = c.post("/api/signals", json=payload, headers=headers)
    assert res1.status_code == 200
    id1 = res1.json()["incident_id"]
    
    res2 = c.post("/api/signals", json=payload, headers=headers)
    assert res2.status_code == 200
    id2 = res2.json()["incident_id"]
    
    assert id1 == id2

def test_lifecycle_9_health_check(setup_teardown):
    c = setup_teardown
    res = c.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "sentinelops"}

def test_lifecycle_10_list_incidents(setup_teardown):
    c = setup_teardown
    res = c.get("/api/incidents")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_lifecycle_11_approve_nonexistent_plan(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    res = c.post("/api/plans/9999/approve", headers=headers)
    assert res.status_code == 404

def test_lifecycle_12_deny_nonexistent_plan(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    res = c.post("/api/plans/9999/deny", headers=headers)
    assert res.status_code == 404

def test_lifecycle_13_valid_csv_ingestion(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    csv_data = "resource,symptom,action_taken,success,timestamp\npod/api-1,OOMKilled,restart_pod,1,2026-07-09T00:00:00\n"
    res = c.post("/api/ingest", files={"file": ("test.csv", csv_data, "text/csv")}, headers=headers)
    assert res.status_code == 200
    assert res.json()["rows_ingested"] == 1

def test_lifecycle_14_plan_double_approve_error(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    from sentinelops.api import server
    mock_client = create_role_based_mock_client(blast_radius="medium")
    server.get_orch().triage.client_override = mock_client
    server.get_orch().investigation.client_override = mock_client
    server.get_orch().planning.client_override = mock_client
    
    payload = {"resource": "pod/pending-1", "namespace": "default", "raw_context": {}}
    res = c.post("/api/signals", json=payload, headers=headers)
    incident_id = res.json()["incident_id"]
    
    res_list = c.get("/api/incidents")
    incidents = res_list.json()
    inc = next(i for i in incidents if i["id"] == incident_id)
    plan_id = inc["plans"][0]["id"]
    
    res_app1 = c.post(f"/api/plans/{plan_id}/approve", headers=headers)
    assert res_app1.status_code == 200
    
    res_app2 = c.post(f"/api/plans/{plan_id}/approve", headers=headers)
    assert res_app2.status_code == 400

def test_lifecycle_15_confidence_feedback_loop(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    from sentinelops.api import server
    mock_client = create_role_based_mock_client(blast_radius="medium")
    server.get_orch().triage.client_override = mock_client
    server.get_orch().investigation.client_override = mock_client
    server.get_orch().planning.client_override = mock_client
    
    payload = {"resource": "pod/feedback-loop", "namespace": "default", "raw_context": {}}
    res1 = c.post("/api/signals", json=payload, headers=headers)
    inc_id = res1.json()["incident_id"]
    
    res_list = c.get("/api/incidents")
    inc = next(i for i in res_list.json() if i["id"] == inc_id)
    plan = inc["plans"][0]
    initial_confidence = plan["confidence"]
    
    c.post(f"/api/plans/{plan['id']}/approve", headers=headers)
    
    payload2 = {"resource": "pod/feedback-loop-2", "namespace": "default", "raw_context": {}}
    res2 = c.post("/api/signals", json=payload2, headers=headers)
    inc_id2 = res2.json()["incident_id"]
    
    res_list2 = c.get("/api/incidents")
    inc2 = next(i for i in res_list2.json() if i["id"] == inc_id2)
    plan2 = inc2["plans"][0]
    print(f"DEBUG: initial_confidence={initial_confidence}, plan={plan}, inc={inc}")
    
    new_confidence = plan2["confidence"]
    print(f"DEBUG: new_confidence={new_confidence}, plan2={plan2}, inc2={inc2}")
    
    assert new_confidence > initial_confidence
