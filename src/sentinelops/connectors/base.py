"""Base connector interface for Kubernetes clusters."""

from abc import ABC, abstractmethod
from typing import Any, List

from kubernetes import client


class BaseConnector(ABC):
    """Abstract base class for cloud-specific Kubernetes connectors."""

    @abstractmethod
    def get_k8s_client(self, cluster_name: str) -> client.CoreV1Api:
        """Return an authenticated CoreV1Api client for the given cluster."""
        pass

    @abstractmethod
    def get_apps_client(self, cluster_name: str) -> client.AppsV1Api:
        """Return an authenticated AppsV1Api client for the given cluster."""
        pass

    @abstractmethod
    def health_check(self, cluster_name: str) -> dict:
        """Ping the cluster and return status, latency, version info."""
        pass

    @abstractmethod
    def list_clusters(self) -> List[str]:
        """List available cluster names."""
        pass

    @abstractmethod
    def get_cluster_info(self, cluster_name: str) -> dict:
        """Return cluster version, node count, region."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Cleanup resources, close sessions."""
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit — cleanup."""
        self.close()
