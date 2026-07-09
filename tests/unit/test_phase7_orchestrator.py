"""Phase 7 — Orchestrator tests."""

import json
from unittest.mock import MagicMock

import pytest

from sentinelops.memory.graph import IncidentGraph
from sentinelops.memory.store import Store
from sentinelops.models.signal import IncidentSignal
from sentinelops.orchestrator import Orchestrator


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def graph(store):
    return IncidentGraph(store)


def _create_full_mock_client():
    """Mock the OpenAI client for a full run.
    Different calls will return different structured outputs.
    """
    mock_client = MagicMock()
    
    # 1. Triage
    triage_args = json.dumps({
        "symptom_tags": ["OOMKilled"],
        "severity": "high",
        "reasoning": "OOM"
    })
    # 2. Investigation
    inv_args = json.dumps({
        "cause": "Memory Leak",
        "p_diagnosis": 1.0,
        "evidence": {}
    })
    # 3. Planning
    plan_args = json.dumps({
        "action": "restart_pod",
        "params": {"namespace": "default", "pod_name": "test"},
        "blast_radius": "low"
    })
    
    def side_effect(*args, **kwargs):
        model = kwargs.get("model", "")
        # Since we use qwen-plus for all 3, we can't easily distinguish by model.
        # But we can inspect the messages or just pop from a list.
        # Wait, reason() maps all to 'qwen-plus'. We'll just inspect the system prompt.
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


def test_orchestrator_end_to_end_cold_start(store, graph):
    """At cold start, confidence is low, so it requires human arbitration."""
    client = _create_full_mock_client()
    orch = Orchestrator(store, graph, dry_run=True, client_override=client)
    
    signal = IncidentSignal(resource="pod/api", namespace="default", symptom_tags=[], severity="low")
    incident = orch.process_signal(signal)
    
    assert incident.status == "pending"  # Needs human because confidence is ~0.196 (cold start LCB)
    
    # Verify records were created
    plans = store.get_plans(incident.id)
    assert len(plans) == 1
    assert plans[0].gate_decision == "pending_human"
    
    hyps = store.get_hypotheses(incident.id)
    assert len(hyps) == 1
    assert hyps[0].cause == "Memory Leak"


def test_orchestrator_end_to_end_high_confidence(store, graph):
    """If there's enough history, it auto-approves."""
    client = _create_full_mock_client()
    orch = Orchestrator(store, graph, dry_run=True, client_override=client)
    
    # Pre-seed history to push confidence > 0.85
    fr = store.get_or_create_fix_record("restart_pod", "OOMKilled")
    for _ in range(50):
        store.record_outcome(fr.id, success=True)
        
    signal = IncidentSignal(resource="pod/api", namespace="default", symptom_tags=[], severity="low")
    incident = orch.process_signal(signal)
    
    # Confidence is high enough, blast radius is low -> approved!
    # Because it's approved, execution runs and updates status to resolved.
    assert incident.status == "resolved"
    
    plans = store.get_plans(incident.id)
    assert plans[0].gate_decision == "approved"
    assert plans[0].confidence >= 0.85
