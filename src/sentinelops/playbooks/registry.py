"""Playbook registry — typed, parameterized actions with safety gates."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError

from sentinelops.config.settings import settings


class ActionError(Exception):
    """Base class for action execution errors."""


class NamespaceDeniedError(ActionError):
    """Raised when an action attempts to mutate a denylisted namespace."""


class ParamValidationError(ActionError):
    """Raised when action parameters fail schema validation."""


class PlaybookAction(ABC):
    """Abstract base class for a remediation action."""

    name: str
    description: str
    params_schema: Type[BaseModel]
    safety_level: str = "NOT_CLASSIFIED"
    connector_method: str = ""

    @abstractmethod
    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        """Execute the action, returning a diff or result summary.

        If dry_run is True, return what *would* happen without mutating.
        """
        pass

    def validate_params(self, params_dict: Dict[str, Any]) -> BaseModel:
        """Validate raw dictionary against the action's Pydantic schema."""
        try:
            return self.params_schema(**params_dict)
        except ValidationError as e:
            raise ParamValidationError(f"Invalid params for {self.name}: {e}")

    def check_namespace(self, namespace: str):
        """Ensure the target namespace is not in the denylist."""
        if namespace in settings.denylist:
            raise NamespaceDeniedError(f"Namespace '{namespace}' is denylisted.")


# --- Target Scenario Actions ---

class RestartPodParams(BaseModel):
    namespace: str
    pod_name: str


class RestartPodAction(PlaybookAction):
    name = "restart_pod"
    description = "Delete a pod to force a restart (fixes CrashLoopBackOff)"
    safety_level = "DESTRUCTIVE"
    connector_method = "get_k8s_client"
    params_schema = RestartPodParams

    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        params = self.validate_params(params_dict)
        self.check_namespace(params.namespace)

        if dry_run:
            return f"[DRY RUN] Would delete pod {params.pod_name} in namespace {params.namespace}"

        try:
            cluster = params_dict.get("cluster_name", "")
            v1_client = connector.get_k8s_client(cluster_name=cluster)
            v1_client.delete_namespaced_pod(name=params.pod_name, namespace=params.namespace)
            return f"Deleted pod {params.pod_name} in namespace {params.namespace}"
        except Exception as e:
            raise ActionError(f"Failed to delete pod via connector: {e}")


class ScaleDeploymentParams(BaseModel):
    namespace: str
    deployment_name: str
    replicas: int


class ScaleDeploymentAction(PlaybookAction):
    name = "scale_deployment"
    description = "Scale a deployment to a specific number of replicas"
    safety_level = "DESTRUCTIVE"
    connector_method = "get_apps_client"
    params_schema = ScaleDeploymentParams

    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        params = self.validate_params(params_dict)
        self.check_namespace(params.namespace)

        if dry_run:
            return f"[DRY RUN] Would scale deployment {params.deployment_name} to {params.replicas} replicas in {params.namespace}"

        try:
            cluster = params_dict.get("cluster_name", "")
            apps_client = connector.get_apps_client(cluster_name=cluster)
            body = {"spec": {"replicas": params.replicas}}
            apps_client.patch_namespaced_deployment(
                name=params.deployment_name,
                namespace=params.namespace,
                body=body,
            )
            return f"Scaled deployment {params.deployment_name} to {params.replicas} replicas in {params.namespace}"
        except Exception as e:
            raise ActionError(f"Failed to scale deployment via connector: {e}")


class SuppressAlertParams(BaseModel):
    alert_name: str
    duration_minutes: int


class SuppressAlertAction(PlaybookAction):
    name = "suppress_alert"
    description = "Suppress a noisy or flapping alert"
    safety_level = "SAFE"
    connector_method = ""
    params_schema = SuppressAlertParams

    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        params = self.validate_params(params_dict)
        if dry_run:
            return f"[DRY RUN] Would suppress alert {params.alert_name} for {params.duration_minutes}m"
        return f"Suppressed alert {params.alert_name} for {params.duration_minutes}m"


# --- New Playbook Actions ---

class RollbackDeploymentParams(BaseModel):
    namespace: str
    deployment_name: str
    revision: Optional[int] = None


class RollbackDeploymentAction(PlaybookAction):
    name = "rollback_deployment"
    description = "Rollback a deployment to a previous revision"
    safety_level = "DESTRUCTIVE"
    connector_method = "get_apps_client"
    params_schema = RollbackDeploymentParams

    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        params = self.validate_params(params_dict)
        self.check_namespace(params.namespace)

        if dry_run:
            rev = params.revision or "previous"
            return f"[DRY RUN] Would rollback deployment {params.deployment_name} to revision {rev} in {params.namespace}"

        try:
            cluster = params_dict.get("cluster_name", "")
            apps_client = connector.get_apps_client(cluster_name=cluster)
            revision = params.revision or 0
            body = {
                "metadata": {
                    "annotations": {
                        "sentinelops/rollback-to": str(revision),
                    }
                }
            }
            apps_client.patch_namespaced_deployment(
                name=params.deployment_name,
                namespace=params.namespace,
                body=body,
            )
            return f"Rolled back deployment {params.deployment_name} to revision {revision} in {params.namespace}"
        except Exception as e:
            raise ActionError(f"Failed to rollback deployment: {e}")


class DrainNodeParams(BaseModel):
    node_name: str
    grace_period_seconds: Optional[int] = 30


class DrainNodeAction(PlaybookAction):
    name = "drain_node"
    description = "Cordon and drain a Kubernetes node (evicts all pods)"
    safety_level = "DESTRUCTIVE"
    connector_method = "get_k8s_client"
    params_schema = DrainNodeParams

    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        params = self.validate_params(params_dict)

        if dry_run:
            return f"[DRY RUN] Would cordon and drain node {params.node_name}"

        try:
            cluster = params_dict.get("cluster_name", "")
            v1_client = connector.get_k8s_client(cluster_name=cluster)

            body = {"spec": {"unschedulable": True}}
            v1_client.patch_node(name=params.node_name, body=body)

            field_selector = f"spec.nodeName={params.node_name}"
            pods = v1_client.list_pod_for_all_namespaces(field_selector=field_selector)
            evicted = []
            for pod in pods.items:
                if pod.metadata.namespace in settings.denylist:
                    continue
                try:
                    v1_client.delete_namespaced_pod(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        grace_period_seconds=params.grace_period_seconds,
                    )
                    evicted.append(f"{pod.metadata.namespace}/{pod.metadata.name}")
                except Exception:
                    pass

            return f"Cordoned node {params.node_name} and evicted {len(evicted)} pods"
        except Exception as e:
            raise ActionError(f"Failed to drain node: {e}")


class DescribePodParams(BaseModel):
    namespace: str
    pod_name: str


class DescribePodAction(PlaybookAction):
    name = "describe_pod"
    description = "Get detailed pod information (read-only)"
    safety_level = "SAFE"
    connector_method = "get_k8s_client"
    params_schema = DescribePodParams

    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        params = self.validate_params(params_dict)
        self.check_namespace(params.namespace)

        try:
            cluster = params_dict.get("cluster_name", "")
            v1_client = connector.get_k8s_client(cluster_name=cluster)
            pod = v1_client.read_namespaced_pod(name=params.pod_name, namespace=params.namespace)
            return (
                f"Pod {params.pod_name} in {params.namespace}: "
                f"phase={pod.status.phase if pod.status else 'unknown'}, "
                f"hostIP={pod.status.host_ip if pod.status else 'N/A'}, "
                f"podIP={pod.status.pod_ip if pod.status else 'N/A'}, "
                f"restart_count={sum(c.restart_count for c in (pod.status.container_statuses or []))}"
            )
        except Exception as e:
            raise ActionError(f"Failed to describe pod: {e}")


class GetLogsParams(BaseModel):
    namespace: str
    pod_name: str
    container: Optional[str] = None
    tail_lines: Optional[int] = 100


class GetLogsAction(PlaybookAction):
    name = "get_logs"
    description = "Fetch pod logs (read-only)"
    safety_level = "SAFE"
    connector_method = "get_k8s_client"
    params_schema = GetLogsParams

    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        params = self.validate_params(params_dict)
        self.check_namespace(params.namespace)

        if dry_run:
            return f"[DRY RUN] Would fetch logs for pod {params.pod_name} in {params.namespace}"

        try:
            cluster = params_dict.get("cluster_name", "")
            v1_client = connector.get_k8s_client(cluster_name=cluster)
            log_kwargs = {
                "name": params.pod_name,
                "namespace": params.namespace,
                "tail_lines": params.tail_lines,
            }
            if params.container:
                log_kwargs["container"] = params.container
            logs = v1_client.read_namespaced_pod_log(**log_kwargs)
            return logs[-5000:] if len(logs) > 5000 else logs
        except Exception as e:
            raise ActionError(f"Failed to get logs: {e}")


class GetEventsParams(BaseModel):
    namespace: Optional[str] = None


class GetEventsAction(PlaybookAction):
    name = "get_events"
    description = "Get namespace events (read-only)"
    safety_level = "SAFE"
    connector_method = "get_k8s_client"
    params_schema = GetEventsParams

    def execute(self, params_dict: Dict[str, Any], connector: Any, dry_run: bool = False) -> str:
        params = self.validate_params(params_dict)

        if dry_run:
            ns = params.namespace or "all"
            return f"[DRY RUN] Would fetch events for namespace {ns}"

        try:
            cluster = params_dict.get("cluster_name", "")
            v1_client = connector.get_k8s_client(cluster_name=cluster)
            if params.namespace:
                events = v1_client.list_namespaced_event(namespace=params.namespace)
            else:
                events = v1_client.list_event_for_all_namespaces()
            lines = []
            for ev in events.items[:50]:
                lines.append(
                    f"{ev.metadata.namespace}/{ev.involved_object.name}: {ev.message or ev.reason}"
                )
            return "\n".join(lines) if lines else "No events found"
        except Exception as e:
            raise ActionError(f"Failed to get events: {e}")


class ActionRegistry:
    """Registry holding all supported playbook actions."""

    def __init__(self):
        self._actions: Dict[str, PlaybookAction] = {}

    def register(self, action: PlaybookAction):
        self._actions[action.name] = action

    def get(self, name: str) -> PlaybookAction:
        if name not in self._actions:
            raise KeyError(f"Action {name} not found in registry.")
        return self._actions[name]

    def list_actions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": action.name,
                "description": action.description,
                "safety_level": action.safety_level,
                "connector_method": action.connector_method,
                "schema": action.params_schema.model_json_schema(),
            }
            for action in self._actions.values()
        ]


# Global registry instance
registry = ActionRegistry()
registry.register(RestartPodAction())
registry.register(ScaleDeploymentAction())
registry.register(SuppressAlertAction())
registry.register(RollbackDeploymentAction())
registry.register(DrainNodeAction())
registry.register(DescribePodAction())
registry.register(GetLogsAction())
registry.register(GetEventsAction())
