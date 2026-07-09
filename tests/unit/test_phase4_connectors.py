"""Phase 4 — Connectors tests.

Verifies the factory, ABC constraints, and that the MockConnector
provides properly mocked Kubernetes clients.
"""

from unittest.mock import MagicMock

import pytest

from kubernetes import client

from sentinelops.connectors.factory import get_connector
from sentinelops.connectors.mock import MockConnector


def test_factory_resolves_providers():
    """Factory should return appropriate connector instances."""
    mock_conn = get_connector("mock")
    assert isinstance(mock_conn, MockConnector)

    # Unknown provider should raise
    with pytest.raises(ValueError):
        get_connector("unknown_cloud")


def test_mock_connector_yields_mocks():
    """MockConnector must yield MagicMocks of CoreV1Api and AppsV1Api."""
    conn = get_connector("mock")
    
    core_client = conn.get_k8s_client("test-cluster")
    assert isinstance(core_client, MagicMock)
    
    apps_client = conn.get_apps_client("test-cluster")
    assert isinstance(apps_client, MagicMock)


def test_base_connector_abc():
    """Cannot instantiate BaseConnector directly."""
    from sentinelops.connectors.base import BaseConnector
    
    with pytest.raises(TypeError):
        BaseConnector()
