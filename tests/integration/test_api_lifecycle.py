"""Integration tests for the SentinelOps API lifecycle."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import json

from sentinelops.api.server import app, get_store, get_graph, get_orch
from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph
from sentinelops.orchestrator import Orchestrator

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown():
    # Use TestClient with 'with' block to trigger lifespan events
    with TestClient(app) as client:
        # Patch the orchestrator's client inside the app
        from sentinelops.api import server
        
        server.get_store().conn.execute("DELETE FROM incidents")
        server.get_store().conn.execute("DELETE FROM hypotheses")
        server.get_store().conn.execute("DELETE FROM plans")
        server.get_store().conn.execute("DELETE FROM fix_outcomes")
        server.get_store().conn.execute("DELETE FROM fix_records")
        server.get_store().conn.execute("DELETE FROM graph_edges")
        server.get_store().conn.commit()
        server.get_graph().graph.clear()
        
        mock_client = MagicMock()
        def side_effect(*args, **kwargs):
            sys_prompt = kwargs["messages"][0]["content"]
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_tool = MagicMock()
            
            if "Triage" in sys_prompt:
                mock_tool.function.arguments = json.dumps({"symptom_tags": ["OOMKilled"], "severity": "high", "reasoning": "OOM"})
            elif "Investigator" in sys_prompt:
                mock_tool.function.arguments = json.dumps({"cause": "Memory Leak", "p_diagnosis": 1.0, "evidence": {}})
            elif "Planner" in sys_prompt:
                # Use medium blast radius to ensure it goes to pending_human
                mock_tool.function.arguments = json.dumps({"action": "restart_pod", "params": {"namespace": "default", "pod_name": "api"}, "blast_radius": "medium"})
            mock_choice.message.tool_calls = [mock_tool]
            mock_resp.choices = [mock_choice]
            return mock_resp
            
        mock_client.chat.completions.create.side_effect = side_effect
        
        # We need to manually set the client override on the orchestrator's agents
        server.get_orch().triage.client_override = mock_client
        server.get_orch().investigation.client_override = mock_client
        server.get_orch().planning.client_override = mock_client
        
        yield client

def test_full_incident_lifecycle(setup_teardown):
    c = setup_teardown
    
    # 1. POST /api/signals
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    payload = {
        "resource": "pod/test-api",
        "namespace": "default",
        "raw_context": {"error": "OOM"}
    }
    resp = c.post("/api/signals", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "incident_id" in data
    incident_id = data["incident_id"]
    
    # 2. GET /api/incidents
    resp = c.get("/api/incidents")
    assert resp.status_code == 200
    incidents = resp.json()
    assert len(incidents) >= 1
    
    incident = next(i for i in incidents if i["id"] == incident_id)
    assert incident["status"] == "pending"
    assert len(incident["plans"]) > 0
    plan_id = incident["plans"][0]["id"]
    assert incident["plans"][0]["gate_decision"] == "pending_human"
    
    # 3. POST /api/plans/{id}/approve
    resp = c.post(f"/api/plans/{plan_id}/approve", headers=headers)
    assert resp.status_code == 200
    
    # Verify it is resolved
    resp = c.get("/api/incidents")
    incidents = resp.json()
    incident = next(i for i in incidents if i["id"] == incident_id)
    assert incident["status"] == "resolved"

def test_malformed_ingest(setup_teardown):
    c = setup_teardown
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    # Missing columns
    csv_content = b"resource,symptom\npod/a,OOM\n"
    
    res = c.post("/api/ingest", files={"file": ("data.csv", csv_content, "text/csv")}, headers=headers)
    assert res.status_code == 400
