import pytest
from unittest.mock import patch, MagicMock
from sentinelops.connectors.aws import AWSConnector
from sentinelops.config.settings import settings

@pytest.fixture(autouse=True)
def mock_aws_settings():
    settings.EKS_CLUSTER_NAME = "test-cluster"
    settings.AWS_REGION = "us-west-2"
    yield

@patch("sentinelops.connectors.aws.boto3.Session")
@patch("sentinelops.connectors.aws.RequestSigner")
@patch("sentinelops.connectors.aws.client.ApiClient")
def test_aws_connector_get_k8s_client(mock_api_client, mock_signer, mock_session):
    # Setup mocks
    mock_session_inst = MagicMock()
    mock_session.return_value = mock_session_inst
    mock_eks_client = MagicMock()
    mock_session_inst.client.return_value = mock_eks_client
    mock_eks_client.describe_cluster.return_value = {
        "cluster": {
            "endpoint": "https://eks.amazonaws.com",
            "certificateAuthority": {"data": "dGVzdC1jZXJ0"}
        }
    }
    
    mock_signer_inst = MagicMock()
    mock_signer.return_value = mock_signer_inst
    mock_signer_inst.generate_presigned_url.return_value = "https://sts.amazonaws.com"
    
    # Test connector
    connector = AWSConnector()
    client1 = connector.get_k8s_client("test-cluster")
    
    assert client1 is not None
    mock_eks_client.describe_cluster.assert_called_once_with(name="test-cluster")
    
    # Test caching
    client2 = connector.get_k8s_client("test-cluster")
    assert client1 is client2
    # describe_cluster should still have only been called once
    mock_eks_client.describe_cluster.assert_called_once()
