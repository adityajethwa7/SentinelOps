"""Core orchestrator tying A-to-Z execution pipeline together."""

from __future__ import annotations

import gc
import logging
import os
import threading
from typing import Optional

from sentinelops.agents.triage import TriageAgent
from sentinelops.agents.investigation import InvestigationAgent
from sentinelops.agents.planning import PlanningAgent
from sentinelops.agents.arbitration import ArbitrationAgent
from sentinelops.agents.execution import ExecutionAgent
from sentinelops.agents.protocol import AgentPipeline, AgentRole
from sentinelops.connectors.factory import get_connector
from sentinelops.memory.confidence import action_confidence
from sentinelops.memory.graph import IncidentGraph
from sentinelops.memory.store import Store
from sentinelops.models.incident import Hypothesis, Incident, Plan
from sentinelops.models.signal import IncidentSignal


logger = logging.getLogger(__name__)


class Orchestrator:
    """The central brain that coordinates agents and state."""

    def __init__(
        self,
        store: Store,
        graph: IncidentGraph,
        provider: str = "mock",
        dry_run: bool = False,
        client_override=None
    ):
        self.store = store
        self.graph = graph
        self.dry_run = dry_run
        
        self.triage = TriageAgent(client_override=client_override)
        self.investigation = InvestigationAgent(client_override=client_override)
        self.planning = PlanningAgent(client_override=client_override)
        self.arbitration = ArbitrationAgent()
        
        self.connector = get_connector(provider)
        self.execution = ExecutionAgent(store, graph, self.connector)
        self._resource_locks = {}
        self._global_lock = threading.Lock()

    def _get_resource_lock(self, resource: str) -> threading.Lock:
        with self._global_lock:
            if resource not in self._resource_locks:
                self._resource_locks[resource] = threading.Lock()
            return self._resource_locks[resource]

    def _check_memory_pressure(self) -> bool:
        """Check if memory pressure is high. Returns True if we should throttle."""
        if not os.environ.get("SENTINELOPS_MEMORY_PROFILING"):
            return False
        try:
            import psutil
            proc = psutil.Process()
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            if rss_mb > 400:
                gc.collect()
                return True
        except ImportError:
            pass
        return False

    def process_signal(self, signal: IncidentSignal) -> Incident:
        """Process a raw incident signal end-to-end."""
        signal.compute_fingerprint()
        resource_lock = self._get_resource_lock(signal.resource)
        with resource_lock:
            # 0. Check for duplicates using fingerprint (resource + symptom tags)
            open_incidents = self.store.conn.execute(
                "SELECT id FROM incidents WHERE fingerprint = ? AND status != 'resolved'", 
                (signal.fingerprint,)
            ).fetchall()
            if open_incidents:
                # Collapse into existing
                return self.store.get_incident(open_incidents[0][0])
                
            # 1. Triage
            pipeline = AgentPipeline()
            triage_res = self.triage.execute(signal)
            pipeline.record(AgentRole.TRIAGE, AgentRole.INVESTIGATION, triage_res.to_dict())
            
            incident = Incident(
                fingerprint=f"{signal.resource}-{'-'.join(triage_res.symptom_tags)}",
                resource=signal.resource,
                namespace=signal.namespace,
                symptom_tags=triage_res.symptom_tags,
                severity=triage_res.severity,
                raw_context=signal.raw_context,
                provider=signal.provider,
                cluster_name=signal.cluster_name,
            )
            self.store.create_incident(incident)
        
        # 2. Investigation
        inv_res = self.investigation.execute(incident, triage_output=triage_res)
        pipeline.record(AgentRole.INVESTIGATION, AgentRole.PLANNING, inv_res.to_dict())
        
        hyp = Hypothesis(
            incident_id=incident.id,
            cause=inv_res.cause,
            p_diagnosis=inv_res.p_diagnosis,
            evidence=inv_res.evidence
        )
        self.store.create_hypothesis(hyp)
        
        # 3. Memory lookup for past fixes for similar fingerprints
        # (This is where the graph + confidence math comes into play)
        # We inject this into the planning agent indirectly or directly.
        # Actually, the memory subsystem calculates historical confidence.
        # Let's say Planning agent proposes an action, and we then attach our statistical confidence.
        
        # 4. Planning
        plan_res = self.planning.execute(incident, inv_res)
        self.last_pipeline = pipeline
        pipeline.record(AgentRole.PLANNING, AgentRole.ARBITRATION, plan_res.to_dict())
        action_name = plan_res.action
        
        # Look up historical outcomes for this action on this symptom cluster
        symptom_cluster = incident.symptom_tags[0] if incident.symptom_tags else "unknown"
        fix_record = self.store.get_or_create_fix_record(action_name, symptom_cluster)
        
        # Apply Bayesian confidence math
        outcomes = fix_record.outcome_tuples()
        conf = action_confidence(hyp.p_diagnosis, outcomes)
        
        plan = Plan(
            incident_id=incident.id,
            action=action_name,
            params=plan_res.params,
            confidence=conf,
            blast_radius=plan_res.blast_radius
        )
        self.store.create_plan(plan)
        
        # 5. Arbitration
        gate_decision = self.arbitration.evaluate(incident, hyp, plan)
        self.store.update_plan_gate(plan.id, gate_decision)
        plan.gate_decision = gate_decision
        
        # 6. Execution
        if gate_decision == "approved":
            # Auto-approve
            res = self.execution.execute(incident, plan, dry_run=self.dry_run)
            incident.status = "resolved"
        elif gate_decision == "denied":
            # Hard deny
            incident.status = "open"
        else:
            # Pending human. For this prototype, we'll pretend it timed out and defaulted to deny.
            # Real implementation would queue it for Telegram.
            incident.status = "pending"
            
        self.store.update_incident_status(incident.id, incident.status)

        del pipeline
        del triage_res
        del inv_res
        del plan_res
        del hyp
        del fix_record
        del outcomes
        del gate_decision

        if self._check_memory_pressure():
            gc.collect()

        return incident

    def check_timeouts(self):
        """Simulates APScheduler job that times out pending approvals to a safe default."""
        pending_plans = self.store.conn.execute(
            "SELECT id, incident_id FROM plans WHERE gate_decision = 'pending_human'"
        ).fetchall()
        for plan_id, incident_id in pending_plans:
            # Deny by default on timeout to ensure safety
            self.store.update_plan_gate(plan_id, "denied")
            self.store.update_incident_status(incident_id, "open")
            logger.warning(f"Plan {plan_id} for incident {incident_id} timed out. Defaulted to DENIED.")
