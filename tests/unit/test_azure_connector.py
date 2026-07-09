import pytest
from unittest.mock import patch, MagicMock
from sentinelops.connectors.azure import AzureConnector
from sentinelops.config.settings import settings

@pytest.fixture(autouse=True)
def mock_azure_settings():
    settings.AKS_CLUSTER_NAME = "test-cluster"
    settings.AKS_RESOURCE_GROUP = "test-rg"
    settings.AZURE_SUBSCRIPTION_ID = "test-sub"
    settings.AZURE_CLIENT_ID = None
    yield

@patch("sentinelops.connectors.azure.DefaultAzureCredential")
@patch("sentinelops.connectors.azure.ContainerServiceClient")
@patch("sentinelops.connectors.azure.config.new_client_from_config")
@patch("sentinelops.connectors.azure.client.ApiClient")
def test_azure_connector_get_k8s_client(mock_api_client, mock_new_client, mock_csc, mock_default_cred):
    # Setup mocks
    mock_cred_inst = MagicMock()
    mock_default_cred.return_value = mock_cred_inst
    
    mock_aks_client = MagicMock()
    mock_csc.return_value = mock_aks_client
    
    mock_results = MagicMock()
    mock_kubeconfig = MagicMock()
    mock_kubeconfig.value = b"dummy-kubeconfig-data"
    mock_results.kubeconfigs = [mock_kubeconfig]
    
    mock_aks_client.managed_clusters.list_cluster_user_credentials.return_value = mock_results
    
    mock_new_client.return_value = MagicMock()
    
    # Test connector
    connector = AzureConnector()
    client1 = connector.get_k8s_client("test-cluster")
    
    assert client1 is not None
    mock_aks_client.managed_clusters.list_cluster_user_credentials.assert_called_once_with(
        resource_group_name="test-rg",
        resource_name="test-cluster"
    )
    
    # Test caching
    client2 = connector.get_k8s_client("test-cluster")
    assert client1 is client2
    mock_aks_client.managed_clusters.list_cluster_user_credentials.assert_called_once()
