"""Execution agent (Stage F).

Executes an approved plan via the Playbook Registry and updates memory.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sentinelops.memory.graph import IncidentGraph
from sentinelops.memory.store import Store
from sentinelops.models.incident import Incident, Plan
from sentinelops.playbooks.registry import ActionError, registry


logger = logging.getLogger(__name__)


class ExecutionAgent:
    """Executes a remediation plan and writes back outcome to memory."""

    def __init__(self, store: Store, graph: IncidentGraph, connector: getattr):
        self.store = store
        self.graph = graph
        self.connector = connector

    def execute(self, incident: Incident, plan: Plan, dry_run: bool = False) -> str:
        """Execute the plan and record the outcome."""
        action = registry.get(plan.action)
        
        success = False
        result_msg = ""
        
        try:
            # 1. Execute via registry
            result_msg = action.execute(plan.params, self.connector, dry_run=dry_run)
            success = True
        except ActionError as e:
            result_msg = f"Action failed validation: {e}"
            success = False
        except Exception as e:
            result_msg = f"Action raised unexpected error: {e}"
            success = False

        # 2. Write-back to Memory (only if not a dry_run, or if we want to simulate learning in dry run?)
        # Let's say we only write back if it's NOT a dry run, OR if it's explicitly allowed.
        # But for tests, we want to see it update. So we always update, but maybe mock it.
        # Actually, let's write back.
        if not dry_run:
            self._write_back_memory(incident, plan, success)

        return result_msg
        
    def simulate_outcome(self, incident: Incident, plan: Plan, success: bool):
        """Used in test harnesses to bypass actual execution but simulate the outcome."""
        self._write_back_memory(incident, plan, success)
        
    def _write_back_memory(self, incident: Incident, plan: Plan, success: bool):
        # The fix identifier is (action_name, primary_symptom)
        # We pick the first symptom tag as the cluster, or "unknown"
        symptom_cluster = incident.symptom_tags[0] if incident.symptom_tags else "unknown"
        
        # Get or create fix record
        fr = self.store.get_or_create_fix_record(plan.action, symptom_cluster)
        
        # Record outcome
        self.store.record_outcome(fr.id, success, datetime.utcnow())
        
        # Update incident-to-fix graph
        self.graph.link(incident.fingerprint, fr.id, weight=1.0)
