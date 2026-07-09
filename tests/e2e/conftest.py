import os
import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

# 1. Dynamically override DEFAULT_DB_PATH in store.py before anything imports it
TEST_DB_PATH = Path("data/test_sentinelops.db")
import sentinelops.memory.store
sentinelops.memory.store.DEFAULT_DB_PATH = TEST_DB_PATH

# Now import the server application and store
from sentinelops.api.server import app
import sentinelops.api.server as api_server
import sys
sys.modules['api_server'] = api_server
from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph
from sentinelops.orchestrator import Orchestrator

@pytest.fixture(scope="module")
def mock_llm_client():
    mock_client = MagicMock()
    
    # 1. Triage args
    triage_args = json.dumps({
        "symptom_tags": ["CrashLoopBackOff"],
        "severity": "high",
        "reasoning": "Symptom identified in logs"
    })
    # 2. Investigation args
    inv_args = json.dumps({
        "cause": "Memory Leak",
        "p_diagnosis": 0.9,
        "evidence": {"log": "OOM killed"}
    })
    # 3. Planning args
    plan_args = json.dumps({
        "action": "restart_pod",
        "params": {"namespace": "default", "pod_name": "test-pod"},
        "blast_radius": "low"
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
        else:
            mock_tool.function.arguments = "{}"
            
        mock_choice.message.tool_calls = [mock_tool]
        mock_resp.choices = [mock_choice]
        return mock_resp

    mock_client.chat.completions.create.side_effect = side_effect
    return mock_client

@pytest.fixture(scope="module")
def client(mock_llm_client):
    # Ensure test DB is fresh
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
            
    with TestClient(app) as c:
        # Override the agents with mock LLM client
        api_server.get_orch().triage.client_override = mock_llm_client
        api_server.get_orch().investigation.client_override = mock_llm_client
        api_server.get_orch().planning.client_override = mock_llm_client
        yield c

    # Clean up test DB
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
