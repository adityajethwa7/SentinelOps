"""Connector failure-mode tests (Tier 5).

Verifies the system gracefully handles:
  - Unknown provider in factory             → ValueError
  - Mock provider returned for 'mock'
  - Execution agent with ConnectionError connector
  - Execution agent with TimeoutError connector
  - Playbook action failure with bad connector
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
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


@pytest.mark.tier5
def test_connector_factory_unknown_provider(client):
    """Factory raises ValueError for an unrecognised provider string."""
    from sentinelops.connectors.factory import get_connector
    with pytest.raises(ValueError, match="Unknown provider"):
        get_connector("nonexistent_provider")


@pytest.mark.tier5
def test_connector_factory_returns_mock(client):
    """Factory returns a MockConnector for provider 'mock'."""
    from sentinelops.connectors.factory import get_connector
    from sentinelops.connectors.mock import MockConnector
    connector = get_connector("mock")
    assert isinstance(connector, MockConnector)


@pytest.mark.tier5
def test_execution_agent_handles_connector_connection_error(client):
    """Execution agent captures ConnectionError and returns a descriptive message."""
    from sentinelops.agents.execution import ExecutionAgent
    from sentinelops.memory.store import Store
    from sentinelops.memory.graph import IncidentGraph
    from sentinelops.models.incident import Incident, Plan

    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path=db_path)
    graph = IncidentGraph(store)

    bad_connector = MagicMock()
    bad_connector.get_k8s_client.side_effect = ConnectionError(
        "Failed to connect to Kubernetes API"
    )

    agent = ExecutionAgent(store, graph, bad_connector)

    incident = Incident(
        fingerprint="test-fp", resource="pod/test", namespace="default"
    )
    plan = Plan(
        action="restart_pod",
        params={"namespace": "default", "pod_name": "test"},
    )
    store.create_incident(incident)
    plan.incident_id = incident.id
    store.create_plan(plan)

    # Should not crash — ExecutionAgent catches Exception
    result = agent.execute(incident, plan, dry_run=False)
    assert any(word in result.lower() for word in ("fail", "error", "unexpected", "connect"))

    store.close()
    db_path.unlink(missing_ok=True)


@pytest.mark.tier5
def test_execution_agent_handles_connector_timeout(client):
    """Execution agent captures TimeoutError and returns a descriptive message."""
    from sentinelops.agents.execution import ExecutionAgent
    from sentinelops.memory.store import Store
    from sentinelops.memory.graph import IncidentGraph
    from sentinelops.models.incident import Incident, Plan

    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path=db_path)
    graph = IncidentGraph(store)

    bad_connector = MagicMock()
    bad_connector.get_k8s_client.side_effect = TimeoutError(
        "Connection timed out"
    )

    agent = ExecutionAgent(store, graph, bad_connector)

    incident = Incident(
        fingerprint="test-fp", resource="pod/test", namespace="default"
    )
    plan = Plan(
        action="restart_pod",
        params={"namespace": "default", "pod_name": "test"},
    )
    store.create_incident(incident)
    plan.incident_id = incident.id
    store.create_plan(plan)

    result = agent.execute(incident, plan, dry_run=False)
    assert any(word in result.lower() for word in ("fail", "error", "unexpected", "timeout"))

    store.close()
    db_path.unlink(missing_ok=True)


@pytest.mark.tier5
def test_playbook_action_fails_with_bad_connector(client):
    """Playbook RestartPodAction raises ActionError when connector fails."""
    from sentinelops.playbooks.registry import RestartPodAction, ActionError
    from unittest.mock import MagicMock

    action = RestartPodAction()
    bad_connector = MagicMock()
    bad_connector.get_k8s_client.side_effect = ConnectionError(
        "K8s API unreachable"
    )

    # Dry-run succeeds (doesn't touch the connector)
    result = action.execute(
        {"namespace": "default", "pod_name": "test"},
        bad_connector,
        dry_run=True,
    )
    assert "[DRY RUN]" in result

    # Non-dry-run raises ActionError
    with pytest.raises(ActionError, match="Failed to delete pod via connector"):
        action.execute(
            {"namespace": "default", "pod_name": "test"},
            bad_connector,
            dry_run=False,
        )


@pytest.mark.tier5
def test_connector_failure_during_full_auto_approve_flow(client):
    """A failing connector during auto-approval is caught and does not crash the API."""
    from unittest.mock import MagicMock
    from sentinelops.playbooks.registry import ActionError

    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    # Ingest training data so the next signal auto-approves
    csv = (
        "resource,symptom,action_taken,success,timestamp\n"
        "pod/a,CrashLoopBackOff,restart_pod,1,2026-07-09T00:00:00Z\n"
        "pod/b,CrashLoopBackOff,restart_pod,1,2026-07-09T01:00:00Z\n"
        "pod/c,CrashLoopBackOff,restart_pod,1,2026-07-09T02:00:00Z\n"
        "pod/d,CrashLoopBackOff,restart_pod,1,2026-07-09T03:00:00Z\n"
        "pod/e,CrashLoopBackOff,restart_pod,1,2026-07-09T04:00:00Z\n"
    )
    client.post("/api/ingest", files={
        "file": ("train.csv", csv, "text/csv"),
    }, headers=headers)

    # Replace connector on the orchestrator with one that fails
    bad_connector = MagicMock()
    bad_connector.get_k8s_client.side_effect = ConnectionError(
        "K8s API unreachable"
    )
    api_server.orch.connector = bad_connector
    api_server.orch.execution.connector = bad_connector

    # Disable dry-run so it actually invokes the connector
    api_server.orch.dry_run = False

    # Send signal — should auto-approve (confidence high) and hit the bad connector
    resp = client.post("/api/signals", json={
        "resource": "pod/connector-fail-test",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"},
    }, headers=headers)

    # The pipeline must complete without a 500
    assert resp.status_code == 200
    # Incident might show as "resolved" if simulate_outcome is called or "open"
    assert resp.json()["status"] in ("open", "resolved")

    # Restore original state
    api_server.orch.dry_run = True
    from sentinelops.connectors.factory import get_connector
    fresh = get_connector("mock")
    api_server.orch.connector = fresh
    api_server.orch.execution.connector = fresh
