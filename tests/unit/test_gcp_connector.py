import pytest
from unittest.mock import patch, MagicMock
from sentinelops.connectors.gcp import GCPConnector
from sentinelops.config.settings import settings

@pytest.fixture(autouse=True)
def mock_gcp_settings():
    settings.GKE_CLUSTER_NAME = "test-cluster"
    settings.GCP_PROJECT_ID = "test-project"
    settings.GCP_ZONE = "us-central1-a"
    yield

@patch("sentinelops.connectors.gcp.google.auth.default")
@patch("sentinelops.connectors.gcp.container_v1.ClusterManagerClient")
@patch("sentinelops.connectors.gcp.client.ApiClient")
def test_gcp_connector_get_k8s_client(mock_api_client, mock_cluster_client, mock_auth_default):
    # Setup mocks
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"
    mock_auth_default.return_value = (mock_creds, "test-project")
    
    mock_gke_client = MagicMock()
    mock_cluster_client.return_value = mock_gke_client
    mock_cluster_info = MagicMock()
    mock_cluster_info.endpoint = "34.34.34.34"
    mock_cluster_info.master_auth.cluster_ca_certificate = "dGVzdC1jZXJ0"
    mock_gke_client.get_cluster.return_value = mock_cluster_info
    
    # Test connector
    connector = GCPConnector()
    client1 = connector.get_k8s_client("test-cluster")
    
    assert client1 is not None
    expected_name = "projects/test-project/locations/us-central1-a/clusters/test-cluster"
    mock_gke_client.get_cluster.assert_called_once_with(name=expected_name)
    
    # Test caching
    client2 = connector.get_k8s_client("test-cluster")
    assert client1 is client2
    mock_gke_client.get_cluster.assert_called_once()
