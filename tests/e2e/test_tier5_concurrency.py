"""Concurrency and race condition tests (Tier 5).

Tests the system's behaviour under concurrent load:
  - 50 simultaneous signal submissions
  - Rapid approve/deny racing on the same incident
  - Concurrent duplicate signal collapsing
  - Memory store concurrent reads/writes
"""

import pytest
import concurrent.futures
import tempfile
from pathlib import Path
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
def test_50_concurrent_signals_all_succeed(client):
    """50 unique concurrent signal POSTs all return 200."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    def post_signal(i):
        return client.post("/api/signals", json={
            "resource": f"pod/concurrent-{i}",
            "namespace": "default",
            "raw_context": {"idx": i},
        }, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(post_signal, i) for i in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    success = [r for r in results if r.status_code == 200]
    assert len(success) == 50, f"Only {len(success)} of 50 signals succeeded"

    feed = client.get("/api/incidents").json()
    assert len(feed) == 50


@pytest.mark.tier5
def test_rapid_approve_deny_same_incident(client):
    """Rapid concurrent approve/deny on the same plan is handled gracefully."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    resp = client.post("/api/signals", json={
        "resource": "pod/rapid-test",
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"},
    }, headers=headers)
    incident_id = resp.json()["incident_id"]

    feed = client.get("/api/incidents").json()
    incident = next(i for i in feed if i["id"] == incident_id)
    plan_id = incident["plans"][0]["id"]

    def do_approve():
        return client.post(f"/api/plans/{plan_id}/approve", headers=headers)

    def do_deny():
        return client.post(f"/api/plans/{plan_id}/deny", headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f_approve = pool.submit(do_approve)
        f_deny = pool.submit(do_deny)
        r_approve = f_approve.result()
        r_deny = f_deny.result()

    # Both must return valid HTTP statuses — no crashes
    assert r_approve.status_code in (200, 400)
    assert r_deny.status_code in (200, 400)

    # System must remain in a valid state
    feed = client.get("/api/incidents").json()
    incident = next(i for i in feed if i["id"] == incident_id)
    assert incident["status"] in ("open", "resolved")


@pytest.mark.tier5
def test_concurrent_duplicate_signals_collapse(client):
    """Concurrent duplicate signals for the same resource collapse to one incident."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}

    def post_signal(_):
        return client.post("/api/signals", json={
            "resource": "pod/concurrent-dup",
            "namespace": "default",
            "raw_context": {"alertname": "CrashLoopBackOff"},
        }, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(post_signal, i) for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(r.status_code == 200 for r in results)

    incident_ids = {r.json()["incident_id"] for r in results}
    assert len(incident_ids) == 1, f"Expected 1 incident, got {len(incident_ids)}"

    feed = client.get("/api/incidents").json()
    matching = [i for i in feed if i["resource"] == "pod/concurrent-dup"]
    assert len(matching) == 1


@pytest.mark.tier5
def test_memory_store_concurrent_reads_writes_no_corruption(client):
    """Memory store handles concurrent reads/writes without data corruption."""
    from sentinelops.memory.store import Store
    from datetime import datetime

    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path=db_path)

    def write_record(n):
        fr = store.get_or_create_fix_record(f"action_{n}", "CrashLoopBackOff")
        store.record_outcome(fr.id, success=(n % 2 == 0), occurred_at=datetime.utcnow())
        return fr.id

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(write_record, i) for i in range(100)]
        record_ids = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(record_ids) == 100
    assert len(set(record_ids)) == 100

    def read_record(rid):
        return store.get_fix_record(rid)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(read_record, rid) for rid in record_ids]
        records = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(r is not None for r in records)
    assert len(records) == 100
    assert all(len(r.outcomes) == 1 for r in records)

    store.close()
    db_path.unlink(missing_ok=True)
