"""Malformed and extreme payload tests (Tier 5).

Verifies the API correctly rejects or handles:
  - Empty / missing required fields           → 422
  - Extremely long strings (20 KB resource)
  - Oversized raw_context (> 100 KB)          → 413
  - Unicode, emoji, special characters
  - Extra unknown fields (ignored, not rejected)
  - Malformed JSON body                       → 422
"""

import pytest
import json
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
def test_signal_empty_body(client):
    """Empty JSON body (missing all required fields) returns 422."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    resp = client.post("/api/signals", json={}, headers=headers)
    assert resp.status_code == 422


@pytest.mark.tier5
def test_signal_missing_resource(client):
    """Signal without resource field returns 422."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    resp = client.post("/api/signals", json={
        "namespace": "default",
        "raw_context": {},
    }, headers=headers)
    assert resp.status_code == 422


@pytest.mark.tier5
def test_signal_missing_namespace(client):
    """Signal without namespace field returns 422."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    resp = client.post("/api/signals", json={
        "resource": "pod/x",
        "raw_context": {},
    }, headers=headers)
    assert resp.status_code == 422


@pytest.mark.tier5
def test_signal_missing_raw_context(client):
    """Signal without raw_context field returns 422."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    resp = client.post("/api/signals", json={
        "resource": "pod/x",
        "namespace": "default",
    }, headers=headers)
    assert resp.status_code == 422


@pytest.mark.tier5
def test_signal_extremely_long_resource(client):
    """Signal with a 20 KB resource string is accepted."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    very_long = "x" * 20000
    resp = client.post("/api/signals", json={
        "resource": very_long,
        "namespace": "default",
        "raw_context": {"alertname": "CrashLoopBackOff"},
    }, headers=headers)
    assert resp.status_code == 200


@pytest.mark.tier5
def test_signal_oversized_raw_context(client):
    """Signal with raw_context exceeding 100 KB returns 413."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    large_ctx = {"data": "x" * 100001}
    resp = client.post("/api/signals", json={
        "resource": "pod/test",
        "namespace": "default",
        "raw_context": large_ctx,
    }, headers=headers)
    assert resp.status_code == 413


@pytest.mark.tier5
def test_signal_special_chars_unicode_emoji(client):
    """Signal with Unicode, emoji, and special characters is accepted."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    resp = client.post("/api/signals", json={
        "resource": "pod/üñí¢ödé-😱-test",
        "namespace": "default-日本語",
        "raw_context": {
            "alertname": "🔥🔥🔥",
            "msg": "<script>alert('xss')</script>",
            "json_payload": '{"key": "val"}',
        },
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] is not None


@pytest.mark.tier5
def test_signal_extra_unknown_fields(client):
    """Signal with extra unknown fields is accepted (fields ignored by Pydantic)."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    resp = client.post("/api/signals", json={
        "resource": "pod/test",
        "namespace": "default",
        "raw_context": {},
        "unknown_field": "should_be_ignored",
        "another_extra": 42,
        "nested_extra": {"a": 1},
    }, headers=headers)
    assert resp.status_code == 200


@pytest.mark.tier5
def test_malformed_json_body(client):
    """Malformed JSON body returns 422."""
    resp = client.post(
        "/api/signals",
        data="this is not valid json",
        headers={
            "X-API-Key": "sentinelops-hackathon-2026",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 422
