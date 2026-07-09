import base64
import time
from unittest.mock import MagicMock, patch
import pytest

from sentinelops.connectors.aws import AWSConnector
from sentinelops.connectors.gcp import GCPConnector
from sentinelops.connectors.azure import AzureConnector
from sentinelops.playbooks.registry import registry, ActionError


# --- Playbook Actions Tests ---

def test_restart_pod_action_executes_api_call():
    """Verify RestartPodAction calls the connector's CoreV1 client delete method."""
    mock_connector = MagicMock()
    mock_v1 = MagicMock()
    mock_connector.get_k8s_client.return_value = mock_v1

    action = registry.get("restart_pod")
    params = {"namespace": "prod-ns", "pod_name": "app-pod-123"}
    
    result = action.execute(params, connector=mock_connector)
    
    # Assert connector method call
    mock_connector.get_k8s_client.assert_called_once_with(cluster_name="")
    # Assert CoreV1Api method call
    mock_v1.delete_namespaced_pod.assert_called_once_with(name="app-pod-123", namespace="prod-ns")
    assert "Deleted pod app-pod-123" in result


def test_scale_deployment_action_executes_api_call():
    """Verify ScaleDeploymentAction calls the connector's AppsV1 client patch method."""
    mock_connector = MagicMock()
    mock_apps = MagicMock()
    mock_connector.get_apps_client.return_value = mock_apps

    action = registry.get("scale_deployment")
    params = {"namespace": "prod-ns", "deployment_name": "web-api", "replicas": 4}
    
    result = action.execute(params, connector=mock_connector)
    
    # Assert connector method call
    mock_connector.get_apps_client.assert_called_once_with(cluster_name="")
    # Assert AppsV1Api method call
    mock_apps.patch_namespaced_deployment.assert_called_once_with(
        name="web-api",
        namespace="prod-ns",
        body={"spec": {"replicas": 4}}
    )
    assert "Scaled deployment web-api to 4 replicas" in result


def test_playbook_action_raises_action_error_on_failure():
    """Verify playbook actions raise ActionError when K8s API call fails."""
    mock_connector = MagicMock()
    mock_v1 = MagicMock()
    mock_v1.delete_namespaced_pod.side_effect = Exception("API connection timed out")
    mock_connector.get_k8s_client.return_value = mock_v1

    action = registry.get("restart_pod")
    params = {"namespace": "prod-ns", "pod_name": "app-pod-123"}
    
    with pytest.raises(ActionError) as exc:
        action.execute(params, connector=mock_connector)
    assert "Failed to delete pod via connector: API connection timed out" in str(exc.value)


# --- AWS Connector Tests ---

@patch("boto3.Session")
@patch("kubernetes.client.ApiClient")
def test_aws_connector_authenticates(mock_api_client_cls, mock_session_cls):
    """Verify AWSConnector interacts with STS/EKS and returns CoreV1 client."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    
    mock_eks = MagicMock()
    mock_session.client.return_value = mock_eks
    mock_eks.describe_cluster.return_value = {
        "cluster": {
            "endpoint": "https://eks-endpoint.aws.com",
            "certificateAuthority": {"data": base64.b64encode(b"dGVzdC1jYQ==").decode()}
        }
    }
    
    mock_credentials = MagicMock()
    mock_session.get_credentials.return_value = mock_credentials
    
    with patch("sentinelops.connectors.aws.RequestSigner") as mock_signer_cls:
        mock_signer = MagicMock()
        mock_signer_cls.return_value = mock_signer
        mock_signer.generate_presigned_url.return_value = "https://sts.example.com/token"
        
        conn = AWSConnector()
        client_instance = conn.get_k8s_client("my-cluster")
        
        assert client_instance is not None
        mock_eks.describe_cluster.assert_called_with(name="my-cluster")
        mock_signer.generate_presigned_url.assert_called_once()


@patch("boto3.Session")
@patch("time.time")
def test_aws_connector_token_refresh(mock_time, mock_session_cls):
    """Verify AWSConnector caches tokens and refreshes them after expiration."""
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    
    mock_eks = MagicMock()
    mock_session.client.return_value = mock_eks
    mock_eks.describe_cluster.return_value = {
        "cluster": {
            "endpoint": "https://eks-endpoint.aws.com",
            "certificateAuthority": {"data": base64.b64encode(b"dGVzdC1jYQ==").decode()}
        }
    }
    
    mock_credentials = MagicMock()
    mock_session.get_credentials.return_value = mock_credentials
    
    mock_time.return_value = 1000.0
    
    with patch("sentinelops.connectors.aws.RequestSigner") as mock_signer_cls:
        mock_signer = MagicMock()
        mock_signer_cls.return_value = mock_signer
        mock_signer.generate_presigned_url.return_value = "https://sts.example.com/token"
        
        conn = AWSConnector()
        
        # 1. Fetch client (causes call to describe_cluster)
        client1 = conn.get_k8s_client("my-cluster")
        assert mock_eks.describe_cluster.call_count == 1
        
        # 2. Fetch client within expiry window (uses cached client, no describe_cluster call)
        mock_time.return_value = 1500.0
        client2 = conn.get_k8s_client("my-cluster")
        assert mock_eks.describe_cluster.call_count == 1
        assert client1 is client2
        
        # 3. Fetch client after expiry window (forces refresh and call to describe_cluster)
        mock_time.return_value = 1700.0
        client3 = conn.get_k8s_client("my-cluster")
        assert mock_eks.describe_cluster.call_count == 2


# --- GCP Connector Tests ---

@patch("google.auth.default")
@patch("google.cloud.container_v1.ClusterManagerClient")
@patch("google.auth.transport.requests.Request")
def test_gcp_connector_authenticates(mock_request_cls, mock_gke_client_cls, mock_auth_default):
    """Verify GCPConnector retrieves GKE cluster metadata and returns CoreV1 client."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-gcp-token"
    mock_auth_default.return_value = (mock_creds, "fake-project")
    
    mock_gke_client = MagicMock()
    mock_gke_client_cls.return_value = mock_gke_client
    
    mock_cluster = MagicMock()
    mock_cluster.endpoint = "10.0.0.1"
    mock_cluster.master_auth.cluster_ca_certificate = base64.b64encode(b"dGVzdC1jYQ==").decode()
    mock_gke_client.get_cluster.return_value = mock_cluster
    
    conn = GCPConnector()
    client_instance = conn.get_k8s_client("gke-cluster")
    
    assert client_instance is not None
    mock_gke_client.get_cluster.assert_called_once()
    mock_creds.refresh.assert_called_once()


@patch("google.auth.default")
@patch("google.cloud.container_v1.ClusterManagerClient")
@patch("google.auth.transport.requests.Request")
@patch("time.time")
def test_gcp_connector_token_refresh(mock_time, mock_request_cls, mock_gke_client_cls, mock_auth_default):
    """Verify GCPConnector caches and refreshes GKE authentication tokens."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-gcp-token"
    mock_auth_default.return_value = (mock_creds, "fake-project")
    
    mock_gke_client = MagicMock()
    mock_gke_client_cls.return_value = mock_gke_client
    
    mock_cluster = MagicMock()
    mock_cluster.endpoint = "10.0.0.1"
    mock_cluster.master_auth.cluster_ca_certificate = base64.b64encode(b"dGVzdC1jYQ==").decode()
    mock_gke_client.get_cluster.return_value = mock_cluster
    
    mock_time.return_value = 1000.0
    
    conn = GCPConnector()
    
    # 1. Fetch client
    client1 = conn.get_k8s_client("gke-cluster")
    assert mock_gke_client.get_cluster.call_count == 1
    
    # 2. Fetch client within cache expiry
    mock_time.return_value = 1500.0
    client2 = conn.get_k8s_client("gke-cluster")
    assert mock_gke_client.get_cluster.call_count == 1
    assert client1 is client2
    
    # 3. Fetch client after cache expiry (re-authenticates)
    mock_time.return_value = 1700.0
    client3 = conn.get_k8s_client("gke-cluster")
    assert mock_gke_client.get_cluster.call_count == 2


# --- Azure Connector Tests ---

@patch("sentinelops.connectors.azure.DefaultAzureCredential")
@patch("sentinelops.connectors.azure.ContainerServiceClient")
@patch("sentinelops.connectors.azure.config.new_client_from_config")
def test_azure_connector_authenticates(mock_new_client_cls, mock_container_client_cls, mock_default_azure_cred):
    """Verify AzureConnector retrieves user credentials and loads kubeconfig."""
    mock_aks_client = MagicMock()
    mock_container_client_cls.return_value = mock_aks_client
    
    mock_cred_results = MagicMock()
    mock_kubeconfig = MagicMock()
    mock_kubeconfig.value = b"apiVersion: v1\nclusters: []"
    mock_cred_results.kubeconfigs = [mock_kubeconfig]
    mock_aks_client.managed_clusters.list_cluster_user_credentials.return_value = mock_cred_results
    
    mock_api_client = MagicMock()
    mock_new_client_cls.return_value = mock_api_client
    
    conn = AzureConnector()
    client_instance = conn.get_k8s_client("aks-cluster")
    
    assert client_instance is not None
    mock_aks_client.managed_clusters.list_cluster_user_credentials.assert_called_once()
    mock_new_client_cls.assert_called_once()


@patch("sentinelops.connectors.azure.DefaultAzureCredential")
@patch("sentinelops.connectors.azure.ContainerServiceClient")
@patch("sentinelops.connectors.azure.config.new_client_from_config")
@patch("time.time")
def test_azure_connector_token_refresh(mock_time, mock_new_client_cls, mock_container_client_cls, mock_default_azure_cred):
    """Verify AzureConnector caches and refreshes AKS kubeconfigs."""
    mock_aks_client = MagicMock()
    mock_container_client_cls.return_value = mock_aks_client
    
    mock_cred_results = MagicMock()
    mock_kubeconfig = MagicMock()
    mock_kubeconfig.value = b"apiVersion: v1\nclusters: []"
    mock_cred_results.kubeconfigs = [mock_kubeconfig]
    mock_aks_client.managed_clusters.list_cluster_user_credentials.return_value = mock_cred_results
    
    mock_api_client = MagicMock()
    mock_new_client_cls.return_value = mock_api_client
    
    mock_time.return_value = 1000.0
    
    conn = AzureConnector()
    
    # 1. Fetch client
    client1 = conn.get_k8s_client("aks-cluster")
    assert mock_aks_client.managed_clusters.list_cluster_user_credentials.call_count == 1
    
    # 2. Fetch client within cache expiry
    mock_time.return_value = 1500.0
    client2 = conn.get_k8s_client("aks-cluster")
    assert mock_aks_client.managed_clusters.list_cluster_user_credentials.call_count == 1
    assert client1 is client2
    
    # 3. Fetch client after cache expiry
    mock_time.return_value = 1700.0
    client3 = conn.get_k8s_client("aks-cluster")
    assert mock_aks_client.managed_clusters.list_cluster_user_credentials.call_count == 2

