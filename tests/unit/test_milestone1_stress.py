import base64
import time
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
import pytest

from sentinelops.connectors.aws import AWSConnector
from sentinelops.connectors.gcp import GCPConnector
from sentinelops.connectors.azure import AzureConnector

def clean_up_files(file_paths):
    """Ensure any files created during tests are deleted so the test environment is not polluted."""
    for path in file_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"Failed to remove {path}: {e}")

def test_aws_cache_stampede_and_file_leak():
    barrier = threading.Barrier(100)
    describe_cluster_calls = 0
    describe_cluster_lock = threading.Lock()
    
    def mock_describe_cluster(*args, **kwargs):
        nonlocal describe_cluster_calls
        with describe_cluster_lock:
            describe_cluster_calls += 1
        time.sleep(0.05)
        return {
            "cluster": {
                "endpoint": "https://eks-endpoint.aws.com",
                "certificateAuthority": {"data": base64.b64encode(b"dGVzdC1jYQ==").decode()}
            }
        }

    mock_session = MagicMock()
    mock_eks = MagicMock()
    mock_eks.describe_cluster.side_effect = mock_describe_cluster
    mock_session.client.return_value = mock_eks
    mock_session.get_credentials.return_value = MagicMock()

    with patch("boto3.Session", return_value=mock_session), \
         patch("sentinelops.connectors.aws.RequestSigner") as mock_signer_cls, \
         patch("kubernetes.client.ApiClient"):
        
        mock_signer = MagicMock()
        mock_signer.generate_presigned_url.return_value = "https://sts.example.com/token"
        mock_signer_cls.return_value = mock_signer
        
        conn = AWSConnector()
        
        original_named_temp_file = tempfile.NamedTemporaryFile
        temp_files_created = []
        
        def spy_named_temporary_file(*args, **kwargs):
            f = original_named_temp_file(*args, **kwargs)
            temp_files_created.append(f.name)
            return f
            
        try:
            with patch("tempfile.NamedTemporaryFile", side_effect=spy_named_temporary_file):
                def worker():
                    barrier.wait(timeout=5)
                    return conn.get_k8s_client("my-cluster")
                    
                with ThreadPoolExecutor(max_workers=100) as executor:
                    futures = [executor.submit(worker) for _ in range(100)]
                    results = [f.result() for f in futures]
            
            # Assertions
            print(f"\n[AWS] describe_cluster calls: {describe_cluster_calls}")
            print(f"[AWS] Temp files created: {len(temp_files_created)}")
            
            # If lock is present, describe_cluster should be called exactly once
            assert describe_cluster_calls == 1, f"Cache stampede: describe_cluster called {describe_cluster_calls} times instead of 1."
            assert len(temp_files_created) == 1, f"Too many temp files created: {len(temp_files_created)}"
        finally:
            clean_up_files(temp_files_created)


def test_gcp_cache_stampede_and_file_leak():
    barrier = threading.Barrier(100)
    get_cluster_calls = 0
    get_cluster_lock = threading.Lock()
    
    def mock_get_cluster(*args, **kwargs):
        nonlocal get_cluster_calls
        with get_cluster_lock:
            get_cluster_calls += 1
        time.sleep(0.05)
        mock_cluster = MagicMock()
        mock_cluster.endpoint = "10.0.0.1"
        mock_cluster.master_auth.cluster_ca_certificate = base64.b64encode(b"dGVzdC1jYQ==").decode()
        return mock_cluster

    mock_creds = MagicMock()
    mock_creds.token = "fake-gcp-token"
    mock_gke_client = MagicMock()
    mock_gke_client.get_cluster.side_effect = mock_get_cluster

    with patch("google.auth.default", return_value=(mock_creds, "fake-project")), \
         patch("google.cloud.container_v1.ClusterManagerClient", return_value=mock_gke_client), \
         patch("google.auth.transport.requests.Request"), \
         patch("kubernetes.client.ApiClient"):
        
        conn = GCPConnector()
        
        original_named_temp_file = tempfile.NamedTemporaryFile
        temp_files_created = []
        
        def spy_named_temporary_file(*args, **kwargs):
            f = original_named_temp_file(*args, **kwargs)
            temp_files_created.append(f.name)
            return f
            
        try:
            with patch("tempfile.NamedTemporaryFile", side_effect=spy_named_temporary_file):
                def worker():
                    barrier.wait(timeout=5)
                    return conn.get_k8s_client("gke-cluster")
                    
                with ThreadPoolExecutor(max_workers=100) as executor:
                    futures = [executor.submit(worker) for _ in range(100)]
                    results = [f.result() for f in futures]
            
            # Assertions
            print(f"\n[GCP] get_cluster calls: {get_cluster_calls}")
            print(f"[GCP] Temp files created: {len(temp_files_created)}")
            
            # If lock is present, get_cluster should be called exactly once
            assert get_cluster_calls == 1, f"Cache stampede: get_cluster called {get_cluster_calls} times instead of 1."
            assert len(temp_files_created) == 1, f"Too many temp files created: {len(temp_files_created)}"
        finally:
            clean_up_files(temp_files_created)


def test_azure_cache_stampede_and_file_leak():
    barrier = threading.Barrier(100)
    list_creds_calls = 0
    list_creds_lock = threading.Lock()
    
    def mock_list_cluster_user_credentials(*args, **kwargs):
        nonlocal list_creds_calls
        with list_creds_lock:
            list_creds_calls += 1
        time.sleep(0.05)
        mock_cred_results = MagicMock()
        mock_kubeconfig = MagicMock()
        mock_kubeconfig.value = b"apiVersion: v1\nclusters: []"
        mock_cred_results.kubeconfigs = [mock_kubeconfig]
        return mock_cred_results

    mock_aks_client = MagicMock()
    mock_aks_client.managed_clusters.list_cluster_user_credentials.side_effect = mock_list_cluster_user_credentials

    with patch("sentinelops.connectors.azure.DefaultAzureCredential"), \
         patch("sentinelops.connectors.azure.ContainerServiceClient", return_value=mock_aks_client), \
         patch("sentinelops.connectors.azure.config.new_client_from_config"):
        
        conn = AzureConnector()
        
        original_named_temp_file = tempfile.NamedTemporaryFile
        temp_files_created = []
        
        def spy_named_temporary_file(*args, **kwargs):
            f = original_named_temp_file(*args, **kwargs)
            temp_files_created.append(f.name)
            return f
            
        try:
            with patch("tempfile.NamedTemporaryFile", side_effect=spy_named_temporary_file):
                def worker():
                    barrier.wait(timeout=5)
                    return conn.get_k8s_client("aks-cluster")
                    
                with ThreadPoolExecutor(max_workers=100) as executor:
                    futures = [executor.submit(worker) for _ in range(100)]
                    results = [f.result() for f in futures]
            
            # Assertions
            print(f"\n[Azure] list_cluster_user_credentials calls: {list_creds_calls}")
            print(f"[Azure] Temp files created: {len(temp_files_created)}")
            
            # If lock is present, list_cluster_user_credentials should be called exactly once
            assert list_creds_calls == 1, f"Cache stampede: list_cluster_user_credentials called {list_creds_calls} times instead of 1."
            assert len(temp_files_created) == 1, f"Too many temp files created: {len(temp_files_created)}"
        finally:
            clean_up_files(temp_files_created)


def test_azure_sequential_token_refresh_leak():
    # Simulate multiple token refreshes for Azure and check if temporary kubeconfig files are being leaked/left behind
    list_creds_calls = 0
    
    def mock_list_cluster_user_credentials(*args, **kwargs):
        nonlocal list_creds_calls
        list_creds_calls += 1
        mock_cred_results = MagicMock()
        mock_kubeconfig = MagicMock()
        mock_kubeconfig.value = f"apiVersion: v1\nclusters: [{list_creds_calls}]".encode()
        mock_cred_results.kubeconfigs = [mock_kubeconfig]
        return mock_cred_results

    mock_aks_client = MagicMock()
    mock_aks_client.managed_clusters.list_cluster_user_credentials.side_effect = mock_list_cluster_user_credentials

    with patch("sentinelops.connectors.azure.DefaultAzureCredential"), \
         patch("sentinelops.connectors.azure.ContainerServiceClient", return_value=mock_aks_client), \
         patch("sentinelops.connectors.azure.config.new_client_from_config"):
        
        conn = AzureConnector()
        
        original_named_temp_file = tempfile.NamedTemporaryFile
        temp_files_created = []
        
        def spy_named_temporary_file(*args, **kwargs):
            f = original_named_temp_file(*args, **kwargs)
            temp_files_created.append(f.name)
            return f
            
        try:
            current_time = 1000.0
            with patch("time.time", side_effect=lambda: current_time), \
                 patch("tempfile.NamedTemporaryFile", side_effect=spy_named_temporary_file):
                
                # First fetch (creates initial cache and 1 temp file)
                conn.get_k8s_client("aks-cluster")
                
                # Perform 5 cache refreshes by advancing time
                for _ in range(5):
                    current_time += 700.0 # expiry is 600
                    conn.get_k8s_client("aks-cluster")
            
            # Let's count how many temp files are STILL on disk.
            # Ideally, when a new token is fetched and a new temp file is created,
            # any previously created temp files for that cluster should be cleaned up,
            # OR we should reuse the same file and overwrite it.
            # But currently, we expect them to be leaked. Let's find out how many exist.
            existing_files = [path for path in temp_files_created if os.path.exists(path)]
            print(f"\n[Azure Sequential] Temp files created: {len(temp_files_created)}")
            print(f"[Azure Sequential] Temp files remaining on disk: {len(existing_files)}")
            
            # Assert that no more than 1 temp file remains on disk for this connector
            assert len(existing_files) <= 1, f"Temporary file leak detected: {len(existing_files)} files remaining on disk after refreshes."
        finally:
            clean_up_files(temp_files_created)
