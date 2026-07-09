"""Tests for connector expansion — new base methods, factory, config, and playbook actions."""

from unittest.mock import MagicMock, patch

import pytest
from kubernetes import client

from sentinelops.connectors.base import BaseConnector
from sentinelops.connectors.config import (
    AWSConnectorConfig,
    AlibabaConnectorConfig,
    AzureConnectorConfig,
    GCPConnectorConfig,
    MockConnectorConfig,
)
from sentinelops.connectors.factory import (
    _connector_cache,
    close_all,
    get_connector,
    get_connector_health,
    list_providers,
)
from sentinelops.connectors.alibaba import AlibabaConnector
from sentinelops.connectors.aws import AWSConnector
from sentinelops.connectors.azure import AzureConnector
from sentinelops.connectors.gcp import GCPConnector
from sentinelops.connectors.kubernetes_real import KubernetesRealConnector
from sentinelops.connectors.mock import MockConnector
from sentinelops.playbooks.registry import (
    DescribePodAction,
    DrainNodeAction,
    GetEventsAction,
    GetLogsAction,
    RollbackDeploymentAction,
    registry,
)


# ─────────────────────────────────────────────
# 1. Verify all new abstract methods exist
# ─────────────────────────────────────────────

def _check_methods_exist(connector_instance):
    """Ensure all required methods exist on a connector instance."""
    assert hasattr(connector_instance, "health_check")
    assert hasattr(connector_instance, "list_clusters")
    assert hasattr(connector_instance, "get_cluster_info")
    assert hasattr(connector_instance, "close")
    assert hasattr(connector_instance, "__enter__")
    assert hasattr(connector_instance, "__exit__")


def test_abstract_methods_defined():
    """BaseConnector must declare all abstract methods."""
    from sentinelops.connectors.base import BaseConnector

    for name in ("health_check", "list_clusters", "get_cluster_info", "close"):
        method = getattr(BaseConnector, name, None)
        assert method is not None, f"{name} not defined on BaseConnector"
        assert getattr(method, "__isabstractmethod__", False), f"{name} is not abstract on BaseConnector"


def test_mock_connector_has_all_methods():
    conn = get_connector("mock")
    _check_methods_exist(conn)


def test_aws_connector_has_all_methods():
    conn = AWSConnector()
    _check_methods_exist(conn)


def test_azure_connector_has_all_methods():
    conn = AzureConnector()
    _check_methods_exist(conn)


def test_gcp_connector_has_all_methods():
    conn = GCPConnector()
    _check_methods_exist(conn)


def test_alibaba_connector_has_all_methods():
    conn = AlibabaConnector()
    _check_methods_exist(conn)


def test_kubernetes_real_connector_has_all_methods():
    conn = KubernetesRealConnector()
    _check_methods_exist(conn)


# ─────────────────────────────────────────────
# 2. Mock connector method behavior
# ─────────────────────────────────────────────

def test_mock_health_check():
    conn = get_connector("mock")
    result = conn.health_check("test-cluster")
    assert result["status"] == "healthy"
    assert "latency_ms" in result
    assert "version" in result


def test_mock_health_check_fail():
    conn = get_connector("mock")
    conn._simulate_health_fail = True
    result = conn.health_check("test-cluster")
    assert result["status"] == "unhealthy"


def test_mock_list_clusters():
    conn = get_connector("mock")
    clusters = conn.list_clusters()
    assert isinstance(clusters, list)
    assert len(clusters) > 0
    assert "mock-cluster-1" in clusters


def test_mock_get_cluster_info():
    conn = get_connector("mock")
    info = conn.get_cluster_info("my-cluster")
    assert info["name"] == "my-cluster"
    assert "version" in info
    assert "node_count" in info
    assert "region" in info


def test_mock_close():
    conn = get_connector("mock")
    assert conn._closed is False
    conn.close()
    assert conn._closed is True


# ─────────────────────────────────────────────
# 3. Context manager support
# ─────────────────────────────────────────────

def test_context_manager():
    conn = get_connector("mock")
    with conn as c:
        assert c is conn
        assert hasattr(c, "get_k8s_client")
    assert conn._closed is True


# ─────────────────────────────────────────────
# 4. Factory improvements
# ─────────────────────────────────────────────

def test_get_connector_health():
    close_all()
    result = get_connector_health("mock")
    assert result["status"] == "healthy"


def test_list_providers():
    providers = list_providers()
    assert isinstance(providers, list)
    assert "mock" in providers
    assert "aws" in providers
    assert "azure" in providers
    assert "gcp" in providers
    assert "alibaba" in providers


def test_get_connector_caching():
    close_all()
    c1 = get_connector("mock")
    c2 = get_connector("mock")
    assert c1 is c2


def test_close_all():
    _connector_cache.clear()
    c1 = get_connector("mock")
    assert not c1._closed
    close_all()
    assert c1._closed


# ─────────────────────────────────────────────
# 5. AWS connector new methods (mocked)
# ─────────────────────────────────────────────

@patch("sentinelops.connectors.aws.boto3.Session")
def test_aws_health_check(mock_session):
    conn = AWSConnector()
    with patch.object(conn, "_make_session") as mock_make:
        mock_sesh = MagicMock()
        mock_make.return_value = mock_sesh
        mock_sts = MagicMock()
        mock_sesh.client.return_value = mock_sts

        result = conn.health_check("test-cluster")
        assert result["status"] == "healthy"


@patch("sentinelops.connectors.aws.boto3.Session")
def test_aws_health_check_failure(mock_session):
    conn = AWSConnector()
    with patch.object(conn, "_make_session") as mock_make:
        mock_sesh = MagicMock()
        mock_make.return_value = mock_sesh
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = Exception("STS failure")
        mock_sesh.client.return_value = mock_sts

        result = conn.health_check("test-cluster")
        assert result["status"] == "unhealthy"
        assert "STS failure" in result["error"]


@patch("sentinelops.connectors.aws.boto3.Session")
def test_aws_list_clusters(mock_session):
    conn = AWSConnector()
    with patch.object(conn, "_make_session") as mock_make:
        mock_sesh = MagicMock()
        mock_make.return_value = mock_sesh
        mock_eks = MagicMock()
        mock_sesh.client.return_value = mock_eks
        paginator = MagicMock()
        mock_eks.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"clusters": ["cluster-a", "cluster-b"]}]

        clusters = conn.list_clusters()
        assert clusters == ["cluster-a", "cluster-b"]


@patch("sentinelops.connectors.aws.boto3.Session")
def test_aws_close(mock_session):
    conn = AWSConnector()
    assert not conn._closed
    conn.close()
    assert conn._closed


# ─────────────────────────────────────────────
# 6. Azure connector new methods (mocked)
# ─────────────────────────────────────────────

@patch("sentinelops.connectors.azure.DefaultAzureCredential")
@patch("sentinelops.connectors.azure.ContainerServiceClient")
def test_azure_health_check(mock_csc, mock_cred):
    conn = AzureConnector()
    mock_client = MagicMock()
    mock_csc.return_value = mock_client

    result = conn.health_check("test-cluster")
    assert result["status"] == "healthy"


@patch("sentinelops.connectors.azure.DefaultAzureCredential")
@patch("sentinelops.connectors.azure.ContainerServiceClient")
def test_azure_list_clusters(mock_csc, mock_cred):
    from sentinelops.config.settings import settings
    with patch.object(settings, "AKS_RESOURCE_GROUP", "test-rg"), \
         patch.object(settings, "AZURE_SUBSCRIPTION_ID", "test-sub"):
        conn = AzureConnector()
        mock_client = MagicMock()
        mock_csc.return_value = mock_client
        mock_cluster = MagicMock()
        mock_cluster.name = "aks-cluster-1"
        mock_client.managed_clusters.list_by_resource_group.return_value = [mock_cluster]
        mock_client.managed_clusters.list.return_value = [mock_cluster]

        clusters = conn.list_clusters()
        assert "aks-cluster-1" in clusters


# ─────────────────────────────────────────────
# 7. GCP connector new methods (mocked)
# ─────────────────────────────────────────────

@patch("sentinelops.connectors.gcp.google.auth.default")
@patch("sentinelops.connectors.gcp.container_v1.ClusterManagerClient")
def test_gcp_health_check(mock_client_cls, mock_auth):
    conn = GCPConnector()
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"
    mock_auth.return_value = (mock_creds, "test-project")
    mock_gke = MagicMock()
    mock_client_cls.return_value = mock_gke

    result = conn.health_check("test-cluster")
    assert result["status"] == "healthy"


# ─────────────────────────────────────────────
# 8. Alibaba connector new methods (mocked)
# ─────────────────────────────────────────────

def test_alibaba_health_check():
    conn = AlibabaConnector()
    # No cluster configured — health should return unhealthy but not crash
    result = conn.health_check("")
    assert "status" in result


def test_alibaba_list_clusters():
    from sentinelops.config.settings import settings
    settings.ACK_CLUSTER_ID = ""
    conn = AlibabaConnector()
    clusters = conn.list_clusters()
    assert isinstance(clusters, list)


# ─────────────────────────────────────────────
# 9. Connector config validation
# ─────────────────────────────────────────────

def test_aws_config_from_settings():
    config = AWSConnectorConfig.from_settings()
    assert isinstance(config, AWSConnectorConfig)
    assert hasattr(config, "is_configured")


def test_azure_config_from_settings():
    config = AzureConnectorConfig.from_settings()
    assert isinstance(config, AzureConnectorConfig)


def test_gcp_config_from_settings():
    config = GCPConnectorConfig.from_settings()
    assert isinstance(config, GCPConnectorConfig)


def test_alibaba_config_from_settings():
    config = AlibabaConnectorConfig.from_settings()
    assert isinstance(config, AlibabaConnectorConfig)


def test_mock_config_from_settings():
    config = MockConnectorConfig.from_settings()
    assert config.is_configured()


def test_aws_config_is_configured():
    """Should return False when keys are empty."""
    config = AWSConnectorConfig()
    assert config.is_configured() is False


def test_azure_config_is_configured():
    config = AzureConnectorConfig()
    assert config.is_configured() is False


# ─────────────────────────────────────────────
# 10. New playbook actions registered correctly
# ─────────────────────────────────────────────

def test_new_actions_registered():
    """All new actions should be in the registry."""
    for name in ("rollback_deployment", "drain_node", "describe_pod", "get_logs", "get_events"):
        action = registry.get(name)
        assert action is not None
        assert action.safety_level in ("SAFE", "DESTRUCTIVE", "DANGEROUS")


def test_describe_pod_action():
    action = registry.get("describe_pod")
    assert action.safety_level == "SAFE"
    assert action.connector_method == "get_k8s_client"
    assert hasattr(action, "params_schema")


def test_get_logs_action():
    action = registry.get("get_logs")
    assert action.safety_level == "SAFE"
    params = action.params_schema(namespace="default", pod_name="test-pod")
    assert params.tail_lines == 100


def test_get_events_action():
    action = registry.get("get_events")
    assert action.safety_level == "SAFE"
    params = action.params_schema()
    assert params.namespace is None


def test_rollback_deployment_action():
    action = registry.get("rollback_deployment")
    assert action.safety_level == "DESTRUCTIVE"
    assert action.connector_method == "get_apps_client"


def test_drain_node_action():
    action = registry.get("drain_node")
    assert action.safety_level == "DESTRUCTIVE"
    assert action.connector_method == "get_k8s_client"


def test_describe_pod_dry_run():
    action = registry.get("describe_pod")
    mock_conn = MagicMock()
    mock_pod = MagicMock()
    mock_pod.status.phase = "Running"
    mock_pod.status.host_ip = "10.0.0.1"
    mock_pod.status.pod_ip = "192.168.1.1"
    cs = MagicMock()
    cs.restart_count = 2
    mock_pod.status.container_statuses = [cs]
    mock_conn.get_k8s_client.return_value.read_namespaced_pod.return_value = mock_pod

    result = action.execute(
        {"namespace": "default", "pod_name": "nginx-abc123", "cluster_name": ""},
        mock_conn,
    )
    assert "Running" in result
    assert "nginx-abc123" in result


def test_get_logs_dry_run():
    action = registry.get("get_logs")
    result = action.execute(
        {"namespace": "default", "pod_name": "test-pod"},
        MagicMock(),
        dry_run=True,
    )
    assert "[DRY RUN]" in result


def test_get_events_dry_run():
    action = registry.get("get_events")
    result = action.execute(
        {},
        MagicMock(),
        dry_run=True,
    )
    assert "[DRY RUN]" in result


def test_rollback_deployment_dry_run():
    action = registry.get("rollback_deployment")
    result = action.execute(
        {"namespace": "default", "deployment_name": "my-app"},
        MagicMock(),
        dry_run=True,
    )
    assert "[DRY RUN]" in result


def test_drain_node_dry_run():
    action = registry.get("drain_node")
    result = action.execute(
        {"node_name": "worker-1"},
        MagicMock(),
        dry_run=True,
    )
    assert "[DRY RUN]" in result


# ─────────────────────────────────────────────
# 11. List actions includes new fields
# ─────────────────────────────────────────────

def test_list_actions_includes_safety_level():
    actions = registry.list_actions()
    for a in actions:
        assert "safety_level" in a
        assert "connector_method" in a


def test_all_actions_have_safety_level():
    actions = registry.list_actions()
    for a in actions:
        assert a["safety_level"] in ("SAFE", "DESTRUCTIVE", "DANGEROUS", "NOT_CLASSIFIED")


# ─────────────────────────────────────────────
# 12. Existing actions unchanged
# ─────────────────────────────────────────────

def test_existing_actions_still_work():
    action = registry.get("restart_pod")
    assert action.name == "restart_pod"

    action = registry.get("scale_deployment")
    assert action.name == "scale_deployment"

    action = registry.get("suppress_alert")
    assert action.name == "suppress_alert"
