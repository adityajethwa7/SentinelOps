"""Connector configuration validation models."""

from __future__ import annotations

from pydantic import BaseModel

from sentinelops.config.settings import settings


class AWSConnectorConfig(BaseModel):
    access_key_id: str = ""
    secret_access_key: str = ""
    region: str = "us-east-1"
    eks_cluster_name: str = ""

    @classmethod
    def from_settings(cls) -> AWSConnectorConfig:
        return cls(
            access_key_id=settings.AWS_ACCESS_KEY_ID or "",
            secret_access_key=settings.AWS_SECRET_ACCESS_KEY or "",
            region=settings.AWS_REGION or "us-east-1",
            eks_cluster_name=settings.EKS_CLUSTER_NAME or "",
        )

    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)


class AzureConnectorConfig(BaseModel):
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    subscription_id: str = ""
    resource_group: str = ""
    aks_cluster_name: str = ""

    @classmethod
    def from_settings(cls) -> AzureConnectorConfig:
        return cls(
            tenant_id=settings.AZURE_TENANT_ID or "",
            client_id=settings.AZURE_CLIENT_ID or "",
            client_secret=settings.AZURE_CLIENT_SECRET or "",
            subscription_id=settings.AZURE_SUBSCRIPTION_ID or "",
            resource_group=settings.AKS_RESOURCE_GROUP or "",
            aks_cluster_name=settings.AKS_CLUSTER_NAME or "",
        )

    def is_configured(self) -> bool:
        return bool(self.tenant_id and self.client_id and self.client_secret and self.subscription_id)


class GCPConnectorConfig(BaseModel):
    credentials_path: str = ""
    project_id: str = ""
    zone: str = ""
    gke_cluster_name: str = ""

    @classmethod
    def from_settings(cls) -> GCPConnectorConfig:
        return cls(
            credentials_path=settings.GOOGLE_APPLICATION_CREDENTIALS or "",
            project_id=settings.GCP_PROJECT_ID or "",
            zone=settings.GCP_ZONE or "",
            gke_cluster_name=settings.GKE_CLUSTER_NAME or "",
        )

    def is_configured(self) -> bool:
        return bool(self.credentials_path or self.project_id)


class AlibabaConnectorConfig(BaseModel):
    access_key_id: str = ""
    access_key_secret: str = ""
    region: str = "cn-hangzhou"
    ack_cluster_id: str = ""

    @classmethod
    def from_settings(cls) -> AlibabaConnectorConfig:
        return cls(
            access_key_id=settings.ALIBABA_ACCESS_KEY_ID or "",
            access_key_secret=settings.ALIBABA_ACCESS_KEY_SECRET or "",
            region=settings.ALIBABA_REGION or "cn-hangzhou",
            ack_cluster_id=settings.ACK_CLUSTER_ID or "",
        )

    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.access_key_secret)


class MockConnectorConfig(BaseModel):
    simulate_health_fail: bool = False

    @classmethod
    def from_settings(cls) -> MockConnectorConfig:
        return cls()

    def is_configured(self) -> bool:
        return True
