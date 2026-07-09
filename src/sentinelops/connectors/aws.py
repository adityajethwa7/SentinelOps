import base64
import os
import tempfile
import threading
import time
from typing import List

import boto3
from botocore.config import Config as BotoConfig
from botocore.signers import RequestSigner
from kubernetes import client

from sentinelops.connectors.base import BaseConnector
from sentinelops.config.settings import settings


class AWSConnector(BaseConnector):
    """AWS EKS Connector using STS/aws-iam-authenticator-equivalent token generation."""

    MAX_CACHE_SIZE = 10

    def __init__(self):
        super().__init__()
        self._client_cache = {}
        self._lock = threading.Lock()
        self._closed = False
        self._retry_config = BotoConfig(
            retries={"max_attempts": 5, "mode": "adaptive"}
        )

    def _make_session(self):
        session_kwargs = {}
        if settings.AWS_ACCESS_KEY_ID:
            session_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        if settings.AWS_SECRET_ACCESS_KEY:
            session_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        region = settings.AWS_REGION or os.environ.get("AWS_REGION", "us-east-1")
        session_kwargs["region_name"] = region
        return boto3.Session(**session_kwargs)

    def _get_region(self) -> str:
        return settings.AWS_REGION or os.environ.get("AWS_REGION", "us-east-1")

    def _get_cluster_client(self, cluster_name: str, client_type: str):
        target_cluster = cluster_name or settings.EKS_CLUSTER_NAME
        if not target_cluster:
            raise ValueError("No cluster name specified and settings.EKS_CLUSTER_NAME is empty.")

        now = time.time()
        cached = self._client_cache.get(target_cluster)
        if cached and now < cached["expiry"]:
            return cached[client_type]

        with self._lock:
            now = time.time()
            cached = self._client_cache.get(target_cluster)
            if cached and now < cached["expiry"]:
                return cached[client_type]

            expiry = now + 600

            session = self._make_session()
            eks_client = session.client("eks", config=self._retry_config)

            cluster_info = eks_client.describe_cluster(name=target_cluster)
            cluster_data = cluster_info["cluster"]
            endpoint = cluster_data["endpoint"]
            ca_data = cluster_data["certificateAuthority"]["data"]

            ca_cert_path = cached.get("ca_file") if cached else None
            if not ca_cert_path:
                ca_cert_bytes = base64.b64decode(ca_data)
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    f.write(ca_cert_bytes)
                    ca_cert_path = f.name

            signer = RequestSigner(
                service_id="sts",
                region_name=self._get_region(),
                signing_name="sts",
                signature_version="v4",
                credentials=session.get_credentials(),
                event_emitter=session.events,
            )

            params = {
                "method": "GET",
                "url": f"https://sts.{self._get_region()}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
                "headers": {"x-k8s-aws-id": target_cluster},
                "body": {},
                "expires_in": 60,
            }

            url = signer.generate_presigned_url(
                request_dict=params,
                operation_name="GetCallerIdentity",
                expires_in=60,
                method="GET",
            )

            token = "k8s-aws-v1." + base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8").rstrip("=")

            k8s_config = client.Configuration()
            k8s_config.host = endpoint
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
            target = cluster_name or settings.EKS_CLUSTER_NAME
            session = self._make_session()
            sts = session.client("sts", config=self._retry_config)
            sts.get_caller_identity()
            if target:
                eks = session.client("eks", config=self._retry_config)
                eks.describe_cluster(name=target)
            latency_ms = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "provider": "aws",
                "region": self._get_region(),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def list_clusters(self) -> List[str]:
        session = self._make_session()
        eks = session.client("eks", config=self._retry_config)
        clusters = []
        paginator = eks.get_paginator("list_clusters")
        for page in paginator.paginate():
            clusters.extend(page["clusters"])
        return clusters

    def get_cluster_info(self, cluster_name: str) -> dict:
        target = cluster_name or settings.EKS_CLUSTER_NAME
        if not target:
            return {"name": "", "version": "unknown", "node_count": 0, "region": self._get_region()}
        try:
            session = self._make_session()
            eks = session.client("eks", config=self._retry_config)
            info = eks.describe_cluster(name=target)
            cluster_data = info["cluster"]
            node_count = 0
            try:
                ng_list = eks.list_nodegroups(clusterName=target)
                for ng_name in ng_list.get("nodegroups", []):
                    ng_info = eks.describe_nodegroup(clusterName=target, nodegroupName=ng_name)
                    node_count += ng_info["nodegroup"]["scalingConfig"]["desiredSize"]
            except Exception:
                pass
            return {
                "name": cluster_data["name"],
                "version": cluster_data.get("version", "unknown"),
                "node_count": node_count,
                "region": self._get_region(),
            }
        except Exception as e:
            return {"name": target, "version": "unknown", "node_count": 0, "region": self._get_region(), "error": str(e)}

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


