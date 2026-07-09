"""Tests for coverage gaps: graph similarity, factory, alibaba, main entrypoint."""

import pytest
from unittest.mock import patch, MagicMock
from sentinelops.memory.graph import IncidentGraph
from sentinelops.memory.store import Store
from sentinelops.connectors.factory import get_connector
from sentinelops.connectors.mock import MockConnector
from sentinelops.connectors.aws import AWSConnector
from sentinelops.connectors.gcp import GCPConnector
from sentinelops.connectors.azure import AzureConnector
from sentinelops.connectors.alibaba import AlibabaConnector


# --- Graph similarity coverage ---

class TestGraphSimilarity:
    """Cover get_similar_fingerprints and edge/node counts."""

    def test_similar_fingerprints_found(self, tmp_path):
        store = Store(db_path=tmp_path / "test.db")
        graph = IncidentGraph(store)

        # Create a shared fix record node between two fingerprints
        graph.link("fp-A", fix_record_id=1, weight=2.0)
        graph.link("fp-B", fix_record_id=1, weight=3.0)

        similar_to_a = graph.get_similar_fingerprints("fp-A")
        assert "fp-B" in similar_to_a

        similar_to_b = graph.get_similar_fingerprints("fp-B")
        assert "fp-A" in similar_to_b

    def test_similar_fingerprints_empty_for_unknown(self, tmp_path):
        store = Store(db_path=tmp_path / "test.db")
        graph = IncidentGraph(store)
        assert graph.get_similar_fingerprints("nonexistent") == []

    def test_similar_fingerprints_no_shared(self, tmp_path):
        store = Store(db_path=tmp_path / "test.db")
        graph = IncidentGraph(store)
        graph.link("fp-A", fix_record_id=1, weight=1.0)
        graph.link("fp-B", fix_record_id=2, weight=1.0)  # different fix record
        assert graph.get_similar_fingerprints("fp-A") == []

    def test_node_and_edge_count(self, tmp_path):
        store = Store(db_path=tmp_path / "test.db")
        graph = IncidentGraph(store)
        assert graph.node_count == 0
        assert graph.edge_count == 0

        graph.link("fp-X", fix_record_id=10, weight=1.0)
        assert graph.node_count == 2  # fp:fp-X and fr:10
        assert graph.edge_count == 1

    def test_link_increments_existing_weight(self, tmp_path):
        store = Store(db_path=tmp_path / "test.db")
        graph = IncidentGraph(store)
        graph.link("fp-C", fix_record_id=5, weight=1.0)
        graph.link("fp-C", fix_record_id=5, weight=2.0)  # should add
        
        records = graph.get_fix_records_for_fingerprint("fp-C")
        assert len(records) == 1
        assert records[0][1] == 3.0  # 1.0 + 2.0

    def test_load_from_store(self, tmp_path):
        store = Store(db_path=tmp_path / "test.db")
        # Insert edges directly in store
        store.upsert_graph_edge("fp-loaded", 42, 5.0)
        
        # Create a new graph and let it load from store
        graph = IncidentGraph(store)
        records = graph.get_fix_records_for_fingerprint("fp-loaded")
        assert len(records) == 1
        assert records[0] == (42, 5.0)


# --- Connector factory coverage ---

class TestConnectorFactory:
    """Cover all factory branches including alibaba and unknown."""

    def test_factory_aws(self):
        conn = get_connector("aws")
        assert isinstance(conn, AWSConnector)

    def test_factory_gcp(self):
        conn = get_connector("gcp")
        assert isinstance(conn, GCPConnector)

    def test_factory_azure(self):
        conn = get_connector("azure")
        assert isinstance(conn, AzureConnector)

    def test_factory_alibaba(self):
        conn = get_connector("alibaba")
        assert isinstance(conn, AlibabaConnector)

    def test_factory_mock(self):
        conn = get_connector("mock")
        assert isinstance(conn, MockConnector)

    def test_factory_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_connector("digitalocean")

    def test_factory_case_insensitive(self):
        conn = get_connector("AWS")
        assert isinstance(conn, AWSConnector)


# --- Alibaba connector coverage ---

class TestAlibabaConnector:
    """Cover alibaba connector methods with mocked kubeconfig."""

    @patch("sentinelops.connectors.alibaba.config")
    @patch("sentinelops.connectors.alibaba.client")
    def test_get_k8s_client(self, mock_client, mock_config):
        mock_client.CoreV1Api.return_value = MagicMock()
        conn = AlibabaConnector()
        result = conn.get_k8s_client("my-cluster")
        mock_config.load_kube_config.assert_called_once_with(context="my-cluster")
        assert result is not None

    @patch("sentinelops.connectors.alibaba.config")
    @patch("sentinelops.connectors.alibaba.client")
    def test_get_apps_client(self, mock_client, mock_config):
        mock_client.AppsV1Api.return_value = MagicMock()
        conn = AlibabaConnector()
        result = conn.get_apps_client("my-cluster")
        mock_config.load_kube_config.assert_called_once_with(context="my-cluster")
        assert result is not None


# --- Main entrypoint coverage ---

class TestMainEntrypoint:
    """Cover the main.py FastAPI app."""

    def test_main_app_health(self):
        from sentinelops.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "sentinelops"

    def test_main_app_metadata(self):
        from sentinelops.main import app
        assert app.title == "SentinelOps"
        assert "1.0.0" in app.version
