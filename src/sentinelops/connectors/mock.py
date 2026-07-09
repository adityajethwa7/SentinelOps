"""Mock connector for testing."""

from unittest.mock import MagicMock
from typing import Any, Dict, List

from kubernetes import client

from sentinelops.connectors.base import BaseConnector


class MockConnector(BaseConnector):
    """A mock connector for testing without hitting real APIs."""

    def __init__(self):
        super().__init__()
        self.simulate_expiry = False
        self._simulate_health_fail = False
        self._has_refreshed = False
        self._closed = False
        self.mock_core = MagicMock(spec=client.CoreV1Api)
        self.mock_apps = MagicMock(spec=client.AppsV1Api)

    def get_credentials(self) -> Dict[str, Any]:
        return {"token": "mock-token", "region": "mock-region"}

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Mock execution that just returns the input payload as success."""
        if self.simulate_expiry and not self._has_refreshed:
            self._has_refreshed = True
            return {"status": "success", "token_refreshed": True, "action": action, "params": params}
        return {"status": "success", "action": action, "params": params}

    def get_k8s_client(self, cluster_name: str) -> client.CoreV1Api:
        return self.mock_core

    def get_apps_client(self, cluster_name: str) -> client.AppsV1Api:
        return self.mock_apps

    def health_check(self, cluster_name: str) -> dict:
        if self._simulate_health_fail:
            return {"status": "unhealthy", "error": "Simulated health failure", "cluster": cluster_name}
        return {
            "status": "healthy",
            "latency_ms": 5.0,
            "version": "1.28.0",
            "cluster": cluster_name or "mock-cluster-1",
        }

    def list_clusters(self) -> List[str]:
        return ["mock-cluster-1", "mock-cluster-2"]

    def get_cluster_info(self, cluster_name: str) -> dict:
        return {
            "name": cluster_name or "mock-cluster-1",
            "version": "1.28.0",
            "node_count": 3,
            "region": "mock-region-1",
        }

    def close(self) -> None:
        self._closed = True
