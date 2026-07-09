"""Phase 3 — Agent tool-calling tests.

Verifies Triage, Investigation, and Planning agents return 
schema-valid output using a mocked Qwen client.
"""

import json
from unittest.mock import MagicMock

import pytest

from sentinelops.agents.triage import TriageAgent
from sentinelops.agents.investigation import InvestigationAgent
from sentinelops.agents.planning import PlanningAgent
from sentinelops.models.incident import Hypothesis, Incident
from sentinelops.models.signal import IncidentSignal


def _create_mock_client(tool_args: dict) -> MagicMock:
    """Create a mock OpenAI client that returns the specified tool arguments."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_tool_call = MagicMock()
    
    mock_tool_call.function.arguments = json.dumps(tool_args)
    mock_choice.message.tool_calls = [mock_tool_call]
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def test_triage_agent():
    """Triage agent should extract tags and severity."""
    mock_args = {
        "symptom_tags": ["CrashLoopBackOff", "OOMKilled"],
        "severity": "high",
        "reasoning": "Memory limit exceeded."
    }
    client = _create_mock_client(mock_args)
    agent = TriageAgent(client_override=client)
    
    signal = IncidentSignal(resource="deploy/test", namespace="default", symptom_tags=[], severity="low")
    result = agent.execute(signal)
    
    assert result.symptom_tags == ["CrashLoopBackOff", "OOMKilled"]
    assert result.severity == "high"
    assert result.reasoning == "Memory limit exceeded."


def test_investigation_agent():
    """Investigation agent should propose a hypothesis."""
    mock_args = {
        "cause": "OOMKilled due to low limits",
        "p_diagnosis": 0.85,
        "evidence": {"last_state": "OOMKilled"}
    }
    client = _create_mock_client(mock_args)
    agent = InvestigationAgent(client_override=client)
    
    incident = Incident(resource="deploy/test")
    result = agent.execute(incident)
    
    assert result.cause == "OOMKilled due to low limits"
    assert result.p_diagnosis == 0.85
    assert result.evidence == {"last_state": "OOMKilled"}


def test_planning_agent():
    """Planning agent should select an action and params."""
    mock_args = {
        "action": "restart_pod",
        "params": {"namespace": "default", "pod_name": "test-pod"},
        "blast_radius": "low"
    }
    client = _create_mock_client(mock_args)
    agent = PlanningAgent(client_override=client)
    
    incident = Incident(resource="deploy/test")
    hyp = Hypothesis(cause="OOM", p_diagnosis=0.9)
    result = agent.execute(incident, hyp)
    assert result.action == "restart_pod"
    assert result.params == {"namespace": "default", "pod_name": "test-pod"}
    assert result.blast_radius == "low"


def test_qwen_client_tool_call_formatting():
    """Verify that the Qwen client formats tool-call messages correctly."""
    from sentinelops.llm.qwen_client import reason
    
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.function.arguments = json.dumps({"test_arg": "value"})
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "function": {"name": "test_func", "parameters": {}}}]
    
    res = reason("triage", messages, tools=tools, client_override=mock_client)
    
    assert res == {"test_arg": "value"}
    mock_client.chat.completions.create.assert_called_once_with(
        model="qwen-plus",
        messages=messages,
        tools=tools,
        temperature=0.2
    )
