import pytest
import sqlite3
from pathlib import Path

def test_bayesian_learning_and_autonomous_execution(client):
    """Verify historical ingest increases confidence to trigger auto-approval (Tier 3)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    # 1. Ingest historical data
    csv_content = (
        "resource,symptom,action_taken,success,timestamp\n"
        "pod/a,CrashLoopBackOff,restart_pod,1,2026-07-09T00:00:00Z\n"
        "pod/b,CrashLoopBackOff,restart_pod,1,2026-07-09T01:00:00Z\n"
        "pod/c,CrashLoopBackOff,restart_pod,1,2026-07-09T02:00:00Z\n"
        "pod/d,CrashLoopBackOff,restart_pod,1,2026-07-09T03:00:00Z\n"
        "pod/e,CrashLoopBackOff,restart_pod,1,2026-07-09T04:00:00Z\n"
    )
    files = {"file": ("history.csv", csv_content, "text/csv")}
    resp = client.post("/api/ingest", files=files, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["rows_ingested"] == 5
    
    # 2. Send signal and verify auto-approval
    payload = {
        "resource": "pod/prod-database",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"}
    }
    resp = client.post("/api/signals", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"  # immediately resolved because of high confidence

def test_audit_logging(client):
    """Verify E2E actions produce immutable audit logs in SQLite store (Tier 3)."""
    # Query test db using direct SQLite query to verify audit logs
    from sentinelops.memory.store import DEFAULT_DB_PATH
    conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("SELECT action, user FROM audit_logs ORDER BY id DESC")
    logs = cursor.fetchall()
    conn.close()
    
    # Verify audit entries are present
    actions = [l[0] for l in logs]
    assert "HISTORICAL_INGEST" in actions
    assert "AUTONOMOUS_EXECUTION" in actions
