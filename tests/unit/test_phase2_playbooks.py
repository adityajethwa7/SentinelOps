"""Phase 2 — Playbook registry tests.

Verifies denylist, param validation, and dry-run capabilities.
"""

from __future__ import annotations

import pytest

from sentinelops.config.settings import settings
from sentinelops.playbooks.registry import (
    NamespaceDeniedError,
    ParamValidationError,
    registry,
)


def test_registry_contains_actions():
    """Registry should be pre-populated with core actions."""
    actions = registry.list_actions()
    assert len(actions) >= 3
    names = [a["name"] for a in actions]
    assert "restart_pod" in names
    assert "scale_deployment" in names
    assert "suppress_alert" in names


def test_invalid_params_rejected():
    """Actions must reject invalid parameters."""
    action = registry.get("restart_pod")
    
    # Missing required 'pod_name'
    with pytest.raises(ParamValidationError) as exc:
        action.execute({"namespace": "default"}, connector=None)
    assert "pod_name" in str(exc.value)

    # Wrong type for 'replicas'
    scale_action = registry.get("scale_deployment")
    with pytest.raises(ParamValidationError) as exc:
        scale_action.execute(
            {"namespace": "default", "deployment_name": "app", "replicas": "not_an_int"},
            connector=None
        )
    assert "replicas" in str(exc.value)


def test_denylisted_namespace_raises(monkeypatch):
    """Actions must refuse to operate on denylisted namespaces."""
    # Ensure kube-system is in the denylist for this test
    monkeypatch.setattr(settings, "DENYLIST_NAMESPACES", "kube-system,kube-public")
    
    action = registry.get("restart_pod")
    
    # Should work for allowed namespace
    res = action.execute({"namespace": "default", "pod_name": "app-123"}, connector=None, dry_run=True)
    assert "DRY RUN" in res
    
    # Should raise for denylisted namespace
    with pytest.raises(NamespaceDeniedError) as exc:
        action.execute({"namespace": "kube-system", "pod_name": "coredns-123"}, connector=None, dry_run=True)
    assert "kube-system" in str(exc.value)


def test_dry_run_support():
    """All actions must support dry_run without mutating state."""
    # Test restart_pod
    action = registry.get("restart_pod")
    res = action.execute({"namespace": "default", "pod_name": "test"}, connector=None, dry_run=True)
    assert "[DRY RUN] Would delete pod test in namespace default" in res
    
    # Test scale_deployment
    action2 = registry.get("scale_deployment")
    res2 = action2.execute(
        {"namespace": "default", "deployment_name": "web", "replicas": 5},
        connector=None,
        dry_run=True
    )
    assert "[DRY RUN]" in res2
    assert "web" in res2
    assert "5" in res2

    # Test suppress_alert
    action3 = registry.get("suppress_alert")
    res3 = action3.execute({"alert_name": "HighCPU", "duration_minutes": 60}, connector=None, dry_run=True)
    assert "[DRY RUN]" in res3
    assert "HighCPU" in res3
    assert "60" in res3
