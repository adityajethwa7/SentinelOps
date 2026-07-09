"""Phase 6 — Execution and write-back tests."""

import pytest

from sentinelops.agents.execution import ExecutionAgent
from sentinelops.memory.graph import IncidentGraph
from sentinelops.memory.store import Store
from sentinelops.models.incident import Incident, Plan


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def graph(store):
    return IncidentGraph(store=store)


def test_execution_write_back(store: Store, graph: IncidentGraph):
    """Simulated execution writes outcomes to memory."""
    agent = ExecutionAgent(store, graph, connector=None)
    
    incident = Incident(
        fingerprint="fp123", 
        resource="pod/test", 
        namespace="default",
        symptom_tags=["OOMKilled"]
    )
    plan = Plan(
        incident_id=1,
        action="restart_pod",
        params={"namespace": "default", "pod_name": "test"},
        confidence=0.9,
        blast_radius="low"
    )
    
    # Simulate a successful fix
    agent.simulate_outcome(incident, plan, success=True)
    
    # Check that it created a fix record and outcome
    fr = store.get_or_create_fix_record("restart_pod", "OOMKilled")
    loaded = store.get_fix_record(fr.id)
    assert len(loaded.outcomes) == 1
    assert loaded.outcomes[0].success is True
    
    # Check that it linked the fingerprint to the fix record
    linked_fixes = graph.get_fix_records_for_fingerprint("fp123")
    assert len(linked_fixes) == 1
    assert linked_fixes[0][0] == fr.id
    assert linked_fixes[0][1] == 1.0  # weight


def test_execution_failure_handled(store: Store, graph: IncidentGraph):
    """Execution gracefully handles errors and returns error strings."""
    agent = ExecutionAgent(store, graph, connector=None)
    incident = Incident(resource="pod/test", namespace="default")
    
    # Invalid action params should be caught by registry validation
    plan = Plan(
        incident_id=1,
        action="restart_pod",
        params={"missing_pod_name": True}, # Invalid
        confidence=0.9,
        blast_radius="low"
    )
    
    res = agent.execute(incident, plan, dry_run=False)
    assert "failed validation" in res
