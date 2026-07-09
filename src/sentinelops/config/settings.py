"""SentinelOps settings — loaded from environment / .env file via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    """Central configuration for SentinelOps.

    All values come from environment variables (or a .env file).
    TUNABLE thresholds are clearly marked.
    """

    # --- Qwen / Alibaba Cloud Model Studio ---
    DASHSCOPE_API_KEY: str = ""
    QWEN_API_KEY: str = ""
    MODELSTUDIO_WORKSPACE_ID: str = ""
    MODELSTUDIO_REGION: str = "ap-southeast-1"

    # --- Cloud provider ---
    CLOUD_PROVIDER: str = Field(default="mock", pattern=r"^(gcp|aws|azure|alibaba|mock)$")

    # --- Telegram HITL ---
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # --- Confidence thresholds (TUNABLE — calibrate by back-test) ---
    LOW_BLAST_BAR: float = 0.35
    PROD_AUTO_BAR: float = 0.55

    # --- Safety ---
    APPROVAL_TIMEOUT_MIN: int = 10
    DENYLIST_NAMESPACES: str = "kube-system,kube-public"

    # --- AWS ---
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    EKS_CLUSTER_NAME: str = ""

    # --- Azure ---
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_SUBSCRIPTION_ID: str = ""
    AKS_RESOURCE_GROUP: str = ""
    AKS_CLUSTER_NAME: str = ""

    # --- GCP ---
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    GCP_PROJECT_ID: str = ""
    GCP_ZONE: str = ""
    GKE_CLUSTER_NAME: str = ""

    # --- Alibaba ---
    ALIBABA_ACCESS_KEY_ID: str = ""
    ALIBABA_ACCESS_KEY_SECRET: str = ""
    ACK_CLUSTER_ID: str = ""
    ALIBABA_REGION: str = "cn-hangzhou"

    @property
    def denylist(self) -> List[str]:
        """Return namespace denylist as a list."""
        return [ns.strip() for ns in self.DENYLIST_NAMESPACES.split(",") if ns.strip()]

    @property
    def modelstudio_base_url(self) -> str:
        """Construct the Model Studio OpenAI-compatible base URL."""
        return (
            f"https://{self.MODELSTUDIO_WORKSPACE_ID}"
            f".{self.MODELSTUDIO_REGION}.maas.aliyuncs.com/compatible-mode/v1"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Module-level singleton — import `settings` elsewhere.
settings = Settings()
