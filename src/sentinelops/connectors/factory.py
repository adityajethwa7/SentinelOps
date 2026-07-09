"""Connector factory for resolving the right cloud provider."""

import threading
import time
from typing import Dict, List, Optional, Tuple

from sentinelops.connectors.base import BaseConnector
from sentinelops.connectors.aws import AWSConnector
from sentinelops.connectors.gcp import GCPConnector
from sentinelops.connectors.azure import AzureConnector
from sentinelops.connectors.alibaba import AlibabaConnector
from sentinelops.connectors.mock import MockConnector
from sentinelops.config.settings import settings

_connector_cache: Dict[str, Tuple[BaseConnector, float]] = {}
_lock = threading.Lock()
_DEFAULT_TTL = 300  # 5 minutes


def _create_connector(provider: str) -> BaseConnector:
    provider = provider.lower()
    if provider == "aws":
        return AWSConnector()
    elif provider == "gcp":
        return GCPConnector()
    elif provider == "azure":
        return AzureConnector()
    elif provider == "alibaba":
        return AlibabaConnector()
    elif provider == "mock":
        return MockConnector()
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_connector(provider: str, ttl: Optional[int] = None) -> BaseConnector:
    """Return the appropriate connector based on provider name.

    Results are cached with a configurable TTL (default 300s).
    Thread-safe via double-checked locking.
    """
    provider = provider.lower()
    ttl_value = ttl or _DEFAULT_TTL
    now = time.time()

    # Fast path (lock-free)
    cached = _connector_cache.get(provider)
    if cached and now < cached[1]:
        return cached[0]

    with _lock:
        # Double-check inside lock
        cached = _connector_cache.get(provider)
        if cached and now < cached[1]:
            return cached[0]

        conn = _create_connector(provider)
        _connector_cache[provider] = (conn, now + ttl_value)
        return conn


def get_connector_health(provider: str) -> dict:
    """Returns health check result for a specific provider's connector."""
    conn = get_connector(provider)
    cluster_name = _get_default_cluster(provider)
    return conn.health_check(cluster_name)


def _get_default_cluster(provider: str) -> str:
    defaults = {
        "aws": settings.EKS_CLUSTER_NAME,
        "azure": settings.AKS_CLUSTER_NAME,
        "gcp": settings.GKE_CLUSTER_NAME,
        "alibaba": settings.ACK_CLUSTER_ID,
        "mock": "mock-cluster-1",
    }
    return defaults.get(provider, "")


def list_providers() -> List[str]:
    """Return list of all supported providers."""
    return ["aws", "azure", "gcp", "alibaba", "mock"]


def close_all() -> None:
    """Close all cached connectors and clear the cache."""
    with _lock:
        for conn, _ in _connector_cache.values():
            try:
                conn.close()
            except Exception:
                pass
        _connector_cache.clear()
