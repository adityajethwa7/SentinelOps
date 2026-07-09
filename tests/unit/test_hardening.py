"""Hardening and Edge-Case tests."""

import json
from unittest.mock import MagicMock

import pytest

from sentinelops.agents.triage import TriageAgent
from sentinelops.models.signal import IncidentSignal
from sentinelops.orchestrator import Orchestrator
from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def graph(store):
    return IncidentGraph(store)


def test_malformed_alert_signal_normalization():
    """Malformed/partial alert signal (missing fields) → normalizer must not crash."""
    # Simulating a signal with missing fields by constructing from raw dict
    raw = {"alertname": "FlappingAlert", "description": "Just some noise"}
    
    # Normalizer should handle missing resource/namespace by providing defaults
    signal = IncidentSignal.from_raw(raw)
    
    assert signal.resource == "unknown"
    assert signal.namespace == "default"
    assert signal.severity == "unknown"
    assert signal.raw_context == raw


def test_llm_invalid_json_graceful_degradation():
    """Qwen returns invalid JSON / no tool call → agent must degrade gracefully, not throw."""
    mock_client = MagicMock()
    # Mocking a response with NO tool calls
    mock_choice = MagicMock()
    mock_choice.message.tool_calls = None
    mock_choice.message.content = "I can't use tools right now."
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    
    agent = TriageAgent(client_override=mock_client)
    signal = IncidentSignal(resource="pod/test", namespace="default", symptom_tags=[], severity="unknown")
    
    res = agent.execute(signal)
    
    # Should degrade gracefully to a safe default rather than raising
    assert res.symptom_tags == ["unknown_symptom"]
    assert res.severity == "high" # default to safe (escalation)


def test_collapse_duplicate_alerts(store, graph):
    """Two alerts on the same resource in one window → must collapse into ONE incident."""
    from .test_phase7_orchestrator import _create_full_mock_client
    orch = Orchestrator(store, graph, dry_run=True, client_override=_create_full_mock_client())
    
    # Create first signal
    sig1 = IncidentSignal(resource="pod/db", namespace="prod", symptom_tags=[], severity="unknown")
    inc1 = orch.process_signal(sig1)
    
    # Create second signal very soon after
    sig2 = IncidentSignal(resource="pod/db", namespace="prod", symptom_tags=[], severity="unknown")
    inc2 = orch.process_signal(sig2)
    
    # The orchestrator should return the existing incident instead of creating a new one
    assert inc1.id == inc2.id
    assert inc2.status != "closed"
    
    # Verify only 1 incident exists in DB
    all_incidents = store.conn.execute("SELECT id FROM incidents").fetchall()
    assert len(all_incidents) == 1


def test_approval_timeout_high_severity(store, graph):
    """Approval timeout on a HIGH-severity incident → safe default fires, logged, never silent."""
    from sentinelops.agents.protocol import TriageOutput, InvestigationOutput, PlanningOutput
    from unittest.mock import MagicMock, PropertyMock
    import json

    orch = Orchestrator(store, graph, dry_run=True, client_override=MagicMock())

    sig = IncidentSignal(resource="pod/db", namespace="prod", symptom_tags=[], severity="high")
    incident = orch.process_signal(sig)

    # Verify a plan was created and is pending_human
    plans = store.get_plans(incident.id)
    assert len(plans) == 1
    assert plans[0].gate_decision == "pending_human"

    # Trigger timeout check
    orch.check_timeouts()

    # Verify the plan was denied as safe default
    plans = store.get_plans(incident.id)
    assert plans[0].gate_decision == "denied"
    incident = store.get_incident(incident.id)
    assert incident.status == "open"

    # Verify audit log captured the timeout
    logs = store.conn.execute(
        "SELECT * FROM audit_logs WHERE action = 'TIMEOUT_SAFE_DEFAULT'"
    ).fetchall()
    assert len(logs) >= 1


def test_flapping_alert_suppressed(store, graph):
    """Flapping case resolving to suppress_alert (no fix)."""
    # If the triage agent determines it's a flapping alert, planning should propose suppress_alert.
    mock_client = MagicMock()
    
    def side_effect(*args, **kwargs):
        sys_prompt = kwargs["messages"][0]["content"]
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_tool = MagicMock()
        if "Triage" in sys_prompt:
            mock_tool.function.arguments = json.dumps({"symptom_tags": ["flapping"], "severity": "low", "reasoning": "noisy"})
        elif "Investigator" in sys_prompt:
            mock_tool.function.arguments = json.dumps({"cause": "Noise", "p_diagnosis": 1.0, "evidence": {}})
        elif "Planner" in sys_prompt:
            mock_tool.function.arguments = json.dumps({"action": "suppress_alert", "params": {"duration_mins": 60}, "blast_radius": "low"})
        mock_choice.message.tool_calls = [mock_tool]
        mock_resp.choices = [mock_choice]
        return mock_resp
    
    mock_client.chat.completions.create.side_effect = side_effect
    orch = Orchestrator(store, graph, dry_run=True, client_override=mock_client)
    
    sig = IncidentSignal(resource="pod/api", namespace="default", symptom_tags=[], severity="unknown")
    incident = orch.process_signal(sig)
    
    plans = store.get_plans(incident.id)
    assert len(plans) == 1
    assert plans[0].action == "suppress_alert"
    
    # Suppress alert has low blast radius, and since it's just suppressing noise, 
    # if confidence is high, it would auto-approve.


def test_connector_token_expiry_mid_run():
    """Connector token expiry mid-run → refresh path exists."""
    from sentinelops.connectors.mock import MockConnector
    from sentinelops.playbooks.registry import ActionError
    
    connector = MockConnector()
    connector.simulate_expiry = True  # We'll add this to MockConnector
    
    # First call should trigger a refresh and then succeed
    res = connector.execute("restart_pod", {"namespace": "default", "pod_name": "test"})
    assert res["status"] == "success"
    assert res["token_refreshed"] is True
