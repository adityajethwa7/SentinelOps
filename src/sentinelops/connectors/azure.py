import base64
import os
import tempfile
import threading
import time
from typing import List

from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.containerservice import ContainerServiceClient
from kubernetes import client, config

from sentinelops.connectors.base import BaseConnector
from sentinelops.config.settings import settings


class AzureConnector(BaseConnector):
    """Azure AKS Connector using AAD/kubelogin/user credentials fetching."""

    MAX_CACHE_SIZE = 10

    def __init__(self):
        super().__init__()
        self._client_cache = {}
        self._lock = threading.Lock()
        self._closed = False

    def _get_credential(self):
        if settings.AZURE_CLIENT_ID and settings.AZURE_CLIENT_SECRET and settings.AZURE_TENANT_ID:
            return ClientSecretCredential(
                tenant_id=settings.AZURE_TENANT_ID,
                client_id=settings.AZURE_CLIENT_ID,
                client_secret=settings.AZURE_CLIENT_SECRET,
            )
        return DefaultAzureCredential()

    def _get_aks_client(self, credential):
        from azure.core.pipeline.policies import RetryPolicy as AzureRetryPolicy
        retry_policy = AzureRetryPolicy(retry_total=3, retry_backoff_factor=0.5)
        return ContainerServiceClient(
            credential, settings.AZURE_SUBSCRIPTION_ID, retry_policy=retry_policy
        )

    def _get_cluster_client(self, cluster_name: str, client_type: str):
        target_cluster = cluster_name or settings.AKS_CLUSTER_NAME
        if not target_cluster:
            raise ValueError("No cluster name specified and settings.AKS_CLUSTER_NAME is empty.")

        now = time.time()
        cached = self._client_cache.get(target_cluster)
        if cached and now < cached["expiry"]:
            return cached[client_type]

        with self._lock:
            now = time.time()
            cached = self._client_cache.get(target_cluster)
            if cached and now < cached["expiry"]:
                return cached[client_type]

            credential = self._get_credential()
            resource_group = settings.AKS_RESOURCE_GROUP
            aks_client = self._get_aks_client(credential)

            cred_results = aks_client.managed_clusters.list_cluster_user_credentials(
                resource_group_name=resource_group,
                resource_name=target_cluster,
            )

            if not cred_results.kubeconfigs:
                raise ValueError("No kubeconfigs returned for Azure AKS cluster.")

            kubeconfig_data = cred_results.kubeconfigs[0].value

            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(kubeconfig_data)
                kubeconfig_path = f.name

            api_client = config.new_client_from_config(config_file=kubeconfig_path)

            core_api = client.CoreV1Api(api_client=api_client)
            apps_api = client.AppsV1Api(api_client=api_client)

            expiry = now + 600

            old_kubeconfig = cached.get("kubeconfig_file") if cached else None
            if old_kubeconfig and os.path.exists(old_kubeconfig):
                try:
                    os.remove(old_kubeconfig)
                except Exception:
                    pass

            self._client_cache[target_cluster] = {
                "core": core_api,
                "apps": apps_api,
                "expiry": expiry,
                "kubeconfig_file": kubeconfig_path,
            }

            if len(self._client_cache) > self.MAX_CACHE_SIZE:
                oldest = min(self._client_cache.keys(),
                             key=lambda k: self._client_cache[k]["expiry"])
                old = self._client_cache.pop(oldest)
                kfile = old.get("kubeconfig_file")
                if kfile and os.path.exists(kfile):
                    try:
                        os.remove(kfile)
                    except Exception:
                        pass

            return self._client_cache[target_cluster][client_type]

    def get_k8s_client(self, cluster_name: str) -> client.CoreV1Api:
        return self._get_cluster_client(cluster_name, "core")

    def get_apps_client(self, cluster_name: str) -> client.AppsV1Api:
        return self._get_cluster_client(cluster_name, "apps")

    def health_check(self, cluster_name: str) -> dict:
        start = time.time()
        try:
            target = cluster_name or settings.AKS_CLUSTER_NAME
            credential = self._get_credential()
            aks_client = self._get_aks_client(credential)
            if target:
                aks_client.managed_clusters.get(
                    resource_group_name=settings.AKS_RESOURCE_GROUP,
                    resource_name=target,
                )
            latency_ms = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "provider": "azure",
                "resource_group": settings.AKS_RESOURCE_GROUP,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def list_clusters(self) -> List[str]:
        credential = self._get_credential()
        aks_client = self._get_aks_client(credential)
        cluster_list = []
        if settings.AKS_RESOURCE_GROUP:
            clusters = aks_client.managed_clusters.list_by_resource_group(
                resource_group_name=settings.AKS_RESOURCE_GROUP
            )
        else:
            clusters = aks_client.managed_clusters.list()
        for cluster in clusters:
            cluster_list.append(cluster.name)
        return cluster_list

    def get_cluster_info(self, cluster_name: str) -> dict:
        target = cluster_name or settings.AKS_CLUSTER_NAME
        if not target:
            return {"name": "", "version": "unknown", "node_count": 0, "region": "unknown"}
        try:
            credential = self._get_credential()
            aks_client = self._get_aks_client(credential)
            cluster = aks_client.managed_clusters.get(
                resource_group_name=settings.AKS_RESOURCE_GROUP,
                resource_name=target,
            )
            node_count = sum(
                (pool.count or 0) for pool in (cluster.agent_pool_profiles or [])
            )
            return {
                "name": cluster.name,
                "version": cluster.kubernetes_version or "unknown",
                "node_count": node_count,
                "region": cluster.location or "unknown",
            }
        except Exception as e:
            return {"name": target, "version": "unknown", "node_count": 0, "region": "unknown", "error": str(e)}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for entry in self._client_cache.values():
            kubeconfig_file = entry.get("kubeconfig_file")
            if kubeconfig_file and os.path.exists(kubeconfig_file):
                try:
                    os.remove(kubeconfig_file)
                except Exception:
                    pass
        self._client_cache.clear()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
