"""Real Kubernetes connector implementation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from sentinelops.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class KubernetesRealConnector(BaseConnector):
    """Executes actions against a real Kubernetes cluster."""

    def __init__(self):
        super().__init__()
        self._closed = False
        self._load_config()

    def _load_config(self):
        """Loads kubeconfig. Works for both in-cluster and local kubeconfig."""
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config.")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig.")
            except Exception as e:
                logger.error(f"Failed to load Kubernetes config: {e}")
                self._client = None
                return

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def get_credentials(self) -> Dict[str, Any]:
        """Credentials handled transparently by kubeconfig."""
        return {"status": "configured"}

    def execute_action(self, action: str, params: Dict[str, Any], dry_run: bool = False) -> str:
        """Execute the requested action against the cluster."""
        if not hasattr(self, 'v1'):
            return "Failed: Kubernetes client not configured."

        if dry_run:
            return f"[DRY-RUN] Would execute {action} with params {params} against real cluster."

        if action == "restart_pod":
            namespace = params.get("namespace", "default")
            pod_name = params.get("pod_name")

            if not pod_name:
                return "Failed: pod_name is required for restart_pod."

            try:
                self.v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
                return f"Successfully restarted pod {pod_name} in namespace {namespace}."
            except ApiException as e:
                return f"Failed to restart pod: {e}"

        elif action == "restart_deployment":
            namespace = params.get("namespace", "default")
            deployment_name = params.get("deployment_name")

            if not deployment_name:
                return "Failed: deployment_name is required for restart_deployment."

            import datetime
            now = datetime.datetime.utcnow().isoformat() + "Z"
            body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": now
                            }
                        }
                    }
                }
            }
            try:
                self.apps_v1.patch_namespaced_deployment(
                    name=deployment_name, namespace=namespace, body=body
                )
                return f"Successfully restarted deployment {deployment_name} in namespace {namespace}."
            except ApiException as e:
                return f"Failed to restart deployment: {e}"

        return f"Failed: Action {action} not natively supported by KubernetesRealConnector yet."

    def get_k8s_client(self, cluster_name: str) -> client.CoreV1Api:
        """Return an authenticated CoreV1Api client."""
        return self.v1

    def get_apps_client(self, cluster_name: str) -> client.AppsV1Api:
        """Return an authenticated AppsV1Api client."""
        return self.apps_v1

    def health_check(self, cluster_name: str) -> dict:
        import time
        start = time.time()
        try:
            if not hasattr(self, 'v1') or self.v1 is None:
                return {"status": "unhealthy", "error": "Kubernetes client not configured"}
            version = client.VersionApi().get_code()
            latency_ms = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "version": version.git_version if hasattr(version, 'git_version') else "unknown",
                "cluster": cluster_name or "default",
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def list_clusters(self) -> List[str]:
        try:
            contexts = config.list_kube_config_contexts()
            if contexts and len(contexts) > 1 and contexts[1]:
                return [contexts[1].get("context", {}).get("cluster", "default")]
            return ["default"]
        except Exception:
            return ["default"]

    def get_cluster_info(self, cluster_name: str) -> dict:
        try:
            if not hasattr(self, 'v1') or self.v1 is None:
                return {"name": cluster_name or "default", "version": "unknown", "node_count": 0, "region": "unknown"}
            nodes = self.v1.list_node()
            node_count = len(nodes.items)
        except Exception:
            node_count = 0
        return {
            "name": cluster_name or "default",
            "version": "unknown",
            "node_count": node_count,
            "region": "unknown",
        }

    def close(self) -> None:
        self._closed = True
