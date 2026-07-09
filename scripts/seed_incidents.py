"""Demo harness for SentinelOps.

Simulates a recurring incident to demonstrate how SentinelOps
builds confidence over time and transitions from requiring human 
arbitration to fully autonomous remediation.
"""

import sys
import os
import time

# Add src to python path so we can run directly from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from sentinelops.memory.graph import IncidentGraph
from sentinelops.memory.store import Store
from sentinelops.models.signal import IncidentSignal
from sentinelops.orchestrator import Orchestrator


def main():
    print("="*60)
    print("🚀 SentinelOps Demo Harness")
    print("="*60)
    
    # Use an in-memory DB for a clean demo run
    from pathlib import Path
    # Start fresh for the demo
    db_path = Path("data/sentinelops.db")
    if db_path.exists():
        db_path.unlink()
        
    store = Store(db_path=db_path)
    graph = IncidentGraph(store)
    
    from sentinelops.config.settings import settings
    has_api_key = bool(settings.QWEN_API_KEY or settings.DASHSCOPE_API_KEY)
    
    if has_api_key:
        print("🔑 API key detected. Running seed incidents with real LLM calls.")
        orch = Orchestrator(store, graph, dry_run=True)
    else:
        print("⚙️ No API key detected. Using mock client fallback.")
        from unittest.mock import MagicMock
        import json
        mock_client = MagicMock()
        def side_effect(*args, **kwargs):
            sys_prompt = kwargs["messages"][0]["content"]
            prompt = kwargs["messages"][1]["content"]
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_tool = MagicMock()
            
            is_flapping = "cache" in str(prompt).lower()
            
            if "Triage" in sys_prompt:
                if is_flapping:
                    mock_tool.function.arguments = json.dumps({"symptom_tags": ["flapping"], "severity": "low", "reasoning": "noisy"})
                else:
                    mock_tool.function.arguments = json.dumps({"symptom_tags": ["OOMKilled"], "severity": "high", "reasoning": "OOM"})
            elif "Investigator" in sys_prompt:
                if is_flapping:
                    mock_tool.function.arguments = json.dumps({"cause": "Noise", "p_diagnosis": 1.0, "evidence": {}})
                else:
                    mock_tool.function.arguments = json.dumps({"cause": "Memory Leak", "p_diagnosis": 1.0, "evidence": {}})
            elif "Planner" in sys_prompt:
                if is_flapping:
                    mock_tool.function.arguments = json.dumps({"action": "suppress_alert", "params": {"duration_mins": 60}, "blast_radius": "low"})
                else:
                    mock_tool.function.arguments = json.dumps({"action": "restart_pod", "params": {"namespace": "default", "pod_name": "api-gateway"}, "blast_radius": "low"})
            mock_choice.message.tool_calls = [mock_tool]
            mock_resp.choices = [mock_choice]
            return mock_resp
        mock_client.chat.completions.create.side_effect = side_effect
        orch = Orchestrator(store, graph, dry_run=True, client_override=mock_client)
    
    signal_template = IncidentSignal(
        resource="pod/api-gateway",
        namespace="default",
        symptom_tags=[],
        severity="high",
        raw_context={"error": "OOMKilled exit code 137"},
    )
    
    flapping_template = IncidentSignal(
        resource="pod/cache",
        namespace="default",
        symptom_tags=[],
        severity="low",
        raw_context={"error": "flapping connection"},
    )
    
    print("\nSimulating recurring OOMKilled incidents on pod/api-gateway...")
    
    for iteration in range(1, 26):
        print(f"\n--- Incident #{iteration} ---")
        
        # 1. Process signal
        incident = orch.process_signal(signal_template)
        plans = store.get_plans(incident.id)
        plan = plans[0]
        
        # 2. Check confidence and gate
        conf_percent = plan.confidence * 100
        print(f"Proposed Action: {plan.action}")
        print(f"System Confidence: {conf_percent:.1f}%")
        print(f"Gate Decision: {plan.gate_decision.upper()}")
        
        # 3. Simulate human interaction if pending
        if plan.gate_decision == "pending_human":
            print("🤖 Human Operator: Approving action...")
            # Simulate human approving and the execution succeeding
            store.update_plan_gate(plan.id, "approved")
            orch.execution.simulate_outcome(incident, plan, success=True)
            store.update_incident_status(incident.id, "closed")
            print("✅ Fix applied successfully. Memory updated.")
        elif plan.gate_decision == "approved":
            print("⚡ AUTONOMOUS REMEDIATION TRIGGERED! No human required.")
            print("✅ Fix applied successfully.")
            # Autonomous execution happens automatically in orchestrator, but we just 
            # simulate the memory update for the graph here since dry_run=True usually skips it.
            orch.execution.simulate_outcome(incident, plan, success=True)
            store.update_incident_status(incident.id, "closed")
            
        time.sleep(0.05)
        
    print("\n" + "="*60)
    print("Simulating Flapping Alert resolving to suppress_alert...")
    print("="*60)
    incident = orch.process_signal(flapping_template)
    plans = store.get_plans(incident.id)
    plan = plans[0]
    print(f"Proposed Action: {plan.action}")
    print(f"Gate Decision: {plan.gate_decision.upper()}")
    if plan.gate_decision == "pending_human":
        print("🤖 Human Operator: Approving suppression...")
        store.update_plan_gate(plan.id, "approved")
        orch.execution.simulate_outcome(incident, plan, success=True)
        store.update_incident_status(incident.id, "resolved")
        print("✅ Alert suppressed successfully. No active fix applied.")
    
    print("\n" + "="*60)
    print("Demo Complete. Confidence trended up until autonomy was reached.")
    print("="*60)

if __name__ == "__main__":
    main()
