import base64
import os
import tempfile
import threading
import time
from typing import List

import google.auth
import google.auth.transport.requests
from google.api_core.retry import Retry as GoogleRetry
from google.cloud import container_v1
from kubernetes import client

from sentinelops.connectors.base import BaseConnector
from sentinelops.config.settings import settings


class GCPConnector(BaseConnector):
    """GCP GKE Connector using Google Auth."""

    MAX_CACHE_SIZE = 10

    def __init__(self):
        super().__init__()
        self._client_cache = {}
        self._lock = threading.Lock()
        self._closed = False
        self._gke_retry = GoogleRetry(
            initial=1.0, maximum=60.0, multiplier=2.0, deadline=120.0
        )

    def _get_credentials_and_project(self):
        if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
            creds, project = google.auth.load_credentials_from_file(
                settings.GOOGLE_APPLICATION_CREDENTIALS,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        else:
            creds, project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        request = google.auth.transport.requests.Request()
        creds.refresh(request)
        return creds, project

    def _get_gke_client(self, creds):
        return container_v1.ClusterManagerClient(credentials=creds)

    def _get_cluster_client(self, cluster_name: str, client_type: str):
        target_cluster = cluster_name or settings.GKE_CLUSTER_NAME
        if not target_cluster:
            raise ValueError("No cluster name specified and settings.GKE_CLUSTER_NAME is empty.")

        now = time.time()
        cached = self._client_cache.get(target_cluster)
        if cached and now < cached["expiry"]:
            return cached[client_type]

        with self._lock:
            now = time.time()
            cached = self._client_cache.get(target_cluster)
            if cached and now < cached["expiry"]:
                return cached[client_type]

            creds, project = self._get_credentials_and_project()
            token = creds.token

            project_id = settings.GCP_PROJECT_ID or project
            zone = settings.GCP_ZONE

            gke_client = self._get_gke_client(creds)
            name = f"projects/{project_id}/locations/{zone}/clusters/{target_cluster}"
            cluster_info = self._gke_retry(gke_client.get_cluster)(name=name)

            endpoint = cluster_info.endpoint
            ca_data = cluster_info.master_auth.cluster_ca_certificate

            ca_cert_path = cached.get("ca_file") if cached else None
            if not ca_cert_path:
                ca_cert_bytes = base64.b64decode(ca_data)
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    f.write(ca_cert_bytes)
                    ca_cert_path = f.name

            expiry = now + 600

            k8s_config = client.Configuration()
            k8s_config.host = f"https://{endpoint}" if not endpoint.startswith("http") else endpoint
            k8s_config.ssl_ca_cert = ca_cert_path
            k8s_config.api_key = {"authorization": "Bearer " + token}

            api_client = client.ApiClient(configuration=k8s_config)
            core_api = client.CoreV1Api(api_client=api_client)
            apps_api = client.AppsV1Api(api_client=api_client)

            self._client_cache[target_cluster] = {
                "core": core_api,
                "apps": apps_api,
                "expiry": expiry,
                "ca_file": ca_cert_path,
            }

            if len(self._client_cache) > self.MAX_CACHE_SIZE:
                oldest = min(self._client_cache.keys(),
                             key=lambda k: self._client_cache[k]["expiry"])
                old = self._client_cache.pop(oldest)
                ca = old.get("ca_file")
                if ca and os.path.exists(ca):
                    try:
                        os.remove(ca)
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
            target = cluster_name or settings.GKE_CLUSTER_NAME
            creds, project = self._get_credentials_and_project()
            gke_client = self._get_gke_client(creds)
            project_id = settings.GCP_PROJECT_ID or project
            if target:
                name = f"projects/{project_id}/locations/{settings.GCP_ZONE}/clusters/{target}"
                self._gke_retry(gke_client.get_cluster)(name=name)
            latency_ms = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "provider": "gcp",
                "project": project_id,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def list_clusters(self) -> List[str]:
        creds, project = self._get_credentials_and_project()
        gke_client = self._get_gke_client(creds)
        project_id = settings.GCP_PROJECT_ID or project
        parent = f"projects/{project_id}/locations/{settings.GCP_ZONE or '-'}"
        clusters = []
        response = self._gke_retry(gke_client.list_clusters)(parent=parent)
        for cluster in response.clusters:
            clusters.append(cluster.name)
        return clusters

    def get_cluster_info(self, cluster_name: str) -> dict:
        target = cluster_name or settings.GKE_CLUSTER_NAME
        if not target:
            return {"name": "", "version": "unknown", "node_count": 0, "region": "unknown"}
        try:
            creds, project = self._get_credentials_and_project()
            gke_client = self._get_gke_client(creds)
            project_id = settings.GCP_PROJECT_ID or project
            name = f"projects/{project_id}/locations/{settings.GCP_ZONE}/clusters/{target}"
            cluster = self._gke_retry(gke_client.get_cluster)(name=name)
            node_count = sum(
                (pool.initial_node_count or 0) for pool in (cluster.node_pools or [])
            )
            return {
                "name": cluster.name,
                "version": cluster.current_master_version or "unknown",
                "node_count": node_count,
                "region": settings.GCP_ZONE or "unknown",
            }
        except Exception as e:
            return {"name": target, "version": "unknown", "node_count": 0, "region": settings.GCP_ZONE or "unknown", "error": str(e)}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for entry in self._client_cache.values():
            ca_file = entry.get("ca_file")
            if ca_file and os.path.exists(ca_file):
                try:
                    os.remove(ca_file)
                except Exception:
                    pass
        self._client_cache.clear()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
