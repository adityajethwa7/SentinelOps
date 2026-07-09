"""Alibaba ACK Connector using RAM."""

import os
import threading
import time
from typing import Any, Dict, List

from kubernetes import client, config

from sentinelops.connectors.base import BaseConnector
from sentinelops.config.settings import settings


def _retry_call(func, max_attempts=3, backoff=1.0):
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(backoff * (2 ** attempt))
    raise last_exc


class AlibabaConnector(BaseConnector):
    """Alibaba ACK Connector using RAM-based kubeconfig authentication."""

    MAX_CACHE_SIZE = 10

    def __init__(self):
        super().__init__()
        self._client_cache = {}
        self._lock = threading.Lock()
        self._closed = False

    def _get_cluster_client(self, cluster_name: str, client_type: str):
        target_cluster = cluster_name or settings.ACK_CLUSTER_ID
        if not target_cluster:
            raise ValueError("No cluster name specified and settings.ACK_CLUSTER_ID is empty.")

        now = time.time()
        cached = self._client_cache.get(target_cluster)
        if cached and now < cached["expiry"]:
            return cached[client_type]

        with self._lock:
            now = time.time()
            cached = self._client_cache.get(target_cluster)
            if cached and now < cached["expiry"]:
                return cached[client_type]

            def _load():
                config.load_kube_config(context=target_cluster)
                return client.CoreV1Api(), client.AppsV1Api()

            core_api, apps_api = _retry_call(_load)
            expiry = now + 600

            self._client_cache[target_cluster] = {
                "core": core_api,
                "apps": apps_api,
                "expiry": expiry,
            }

            if len(self._client_cache) > self.MAX_CACHE_SIZE:
                oldest = min(self._client_cache.keys(),
                             key=lambda k: self._client_cache[k]["expiry"])
                self._client_cache.pop(oldest)

            return self._client_cache[target_cluster][client_type]

    def get_k8s_client(self, cluster_name: str) -> client.CoreV1Api:
        return self._get_cluster_client(cluster_name, "core")

    def get_apps_client(self, cluster_name: str) -> client.AppsV1Api:
        return self._get_cluster_client(cluster_name, "apps")

    def health_check(self, cluster_name: str) -> dict:
        start = time.time()
        try:
            target = cluster_name or settings.ACK_CLUSTER_ID
            if target:
                core = self.get_k8s_client(target)
                core.list_namespace(timeout_seconds=5)
            latency_ms = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "provider": "alibaba",
                "region": settings.ALIBABA_REGION,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def list_clusters(self) -> List[str]:
        cluster = settings.ACK_CLUSTER_ID
        return [cluster] if cluster else []

    def get_cluster_info(self, cluster_name: str) -> dict:
        target = cluster_name or settings.ACK_CLUSTER_ID
        if not target:
            return {"name": "", "version": "unknown", "node_count": 0, "region": settings.ALIBABA_REGION}
        try:
            core = self.get_k8s_client(target)
            nodes = core.list_node(timeout_seconds=10)
            node_count = len(nodes.items)
            return {
                "name": target,
                "version": "unknown",
                "node_count": node_count,
                "region": settings.ALIBABA_REGION,
            }
        except Exception as e:
            return {"name": target, "version": "unknown", "node_count": 0, "region": settings.ALIBABA_REGION, "error": str(e)}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._client_cache.clear()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
