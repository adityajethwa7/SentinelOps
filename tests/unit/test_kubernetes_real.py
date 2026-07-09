import pytest
from unittest.mock import MagicMock, patch
from kubernetes.client.rest import ApiException
from kubernetes.config import ConfigException
from sentinelops.connectors.kubernetes_real import KubernetesRealConnector

@patch("sentinelops.connectors.kubernetes_real.config")
@patch("sentinelops.connectors.kubernetes_real.client")
def test_kubernetes_real_connector_init_success(mock_client, mock_config):
    mock_config.ConfigException = ConfigException
    # Test successful initialization
    mock_config.load_incluster_config.side_effect = ConfigException("Not in cluster")
    mock_config.load_kube_config.return_value = True
    
    mock_v1 = MagicMock()
    mock_apps = MagicMock()
    mock_client.CoreV1Api.return_value = mock_v1
    mock_client.AppsV1Api.return_value = mock_apps
    
    connector = KubernetesRealConnector()
    assert connector.get_credentials() == {"status": "configured"}
    assert connector.v1 == mock_v1
    assert connector.apps_v1 == mock_apps

@patch("sentinelops.connectors.kubernetes_real.config")
@patch("sentinelops.connectors.kubernetes_real.client")
def test_kubernetes_real_connector_init_failure(mock_client, mock_config):
    mock_config.ConfigException = ConfigException
    # Test initialization failure when config loading fails completely
    mock_config.load_incluster_config.side_effect = ConfigException("Not in cluster")
    mock_config.load_kube_config.side_effect = Exception("No kubeconfig found")
    
    connector = KubernetesRealConnector()
    assert not hasattr(connector, "v1")

@patch("sentinelops.connectors.kubernetes_real.config")
@patch("sentinelops.connectors.kubernetes_real.client")
def test_kubernetes_real_connector_execute_actions(mock_client, mock_config):
    mock_config.ConfigException = ConfigException
    # Test execute_action methods
    mock_v1 = MagicMock()
    mock_apps = MagicMock()
    mock_client.CoreV1Api.return_value = mock_v1
    mock_client.AppsV1Api.return_value = mock_apps
    
    connector = KubernetesRealConnector()
    
    # 1. execute_action client not configured
    del connector.v1
    res = connector.execute_action("restart_pod", {})
    assert "Failed: Kubernetes client not configured" in res
    
    # Restore v1
    connector.v1 = mock_v1
    
    # 2. dry_run
    res = connector.execute_action("restart_pod", {"pod_name": "test"}, dry_run=True)
    assert "[DRY-RUN]" in res
    
    # 3. restart_pod missing pod_name
    res = connector.execute_action("restart_pod", {})
    assert "Failed: pod_name is required" in res
    
    # 4. restart_pod success
    res = connector.execute_action("restart_pod", {"pod_name": "test-pod", "namespace": "prod"})
    assert "Successfully restarted pod test-pod" in res
    mock_v1.delete_namespaced_pod.assert_called_once_with(name="test-pod", namespace="prod")
    
    # 5. restart_pod ApiException
    mock_v1.delete_namespaced_pod.side_effect = ApiException(status=404, reason="Not Found")
    res = connector.execute_action("restart_pod", {"pod_name": "test-pod"})
    assert "Failed to restart pod" in res
    
    # 6. restart_deployment missing deployment_name
    res = connector.execute_action("restart_deployment", {})
    assert "Failed: deployment_name is required" in res
    
    # 7. restart_deployment success
    res = connector.execute_action("restart_deployment", {"deployment_name": "test-dep", "namespace": "prod"})
    assert "Successfully restarted deployment test-dep" in res
    mock_apps.patch_namespaced_deployment.assert_called_once()
    
    # 8. restart_deployment ApiException
    mock_apps.patch_namespaced_deployment.side_effect = ApiException(status=500, reason="Internal Error")
    res = connector.execute_action("restart_deployment", {"deployment_name": "test-dep"})
    assert "Failed to restart deployment" in res
    
    # 9. Unsupported action
    res = connector.execute_action("delete_namespace", {"namespace": "test"})
    assert "Failed: Action delete_namespace not natively supported" in res
