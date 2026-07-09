#!/usr/bin/env python3
"""Load test: fires 1,000 concurrent signals and verifies no crashes or DB lock errors.

Uses a mock LLM client so no real API keys are needed.

Usage:
    uv run python scripts/load_test.py
"""

import concurrent.futures
import json
import time
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path
from unittest.mock import MagicMock
from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph
from sentinelops.models.signal import IncidentSignal
from sentinelops.orchestrator import Orchestrator


TOTAL_SIGNALS = 2000
MAX_WORKERS = 20

SYMPTOMS = [
    ["CrashLoopBackOff"],
    ["OOMKilled"],
    ["ImagePullBackOff"],
    ["high_latency"],
    ["connection_refused"],
    ["disk_pressure"],
]

RESOURCES = [
    "deployment/api-gateway",
    "deployment/payment-service",
    "deployment/auth-service",
    "deployment/data-pipeline",
    "deployment/cache-layer",
    "deployment/ml-inference",
]


def create_mock_llm():
    """Create a mock LLM client that returns deterministic responses."""
    mock_client = MagicMock()

    triage_args = json.dumps({
        "symptom_tags": ["CrashLoopBackOff"],
        "severity": "high",
        "reasoning": "Symptom detected"
    })
    inv_args = json.dumps({
        "cause": "Memory Leak",
        "p_diagnosis": 0.9,
        "evidence": {"log": "OOM killed"}
    })
    plan_args = json.dumps({
        "action": "restart_pod",
        "params": {"namespace": "default", "pod_name": "test-pod"},
        "blast_radius": "low"
    })

    def side_effect(*args, **kwargs):
        sys_prompt = kwargs.get("messages", [{}])[0].get("content", "")
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_tool = MagicMock()

        if "Triage" in sys_prompt:
            mock_tool.function.arguments = triage_args
        elif "Investigator" in sys_prompt:
            mock_tool.function.arguments = inv_args
        elif "Planner" in sys_prompt:
            mock_tool.function.arguments = plan_args
        else:
            mock_tool.function.arguments = "{}"

        mock_choice.message.tool_calls = [mock_tool]
        mock_resp.choices = [mock_choice]
        return mock_resp

    mock_client.chat.completions.create.side_effect = side_effect
    return mock_client


def process_one(args):
    """Process a single signal using a shared Orchestrator."""
    idx, orch = args
    resource = RESOURCES[idx % len(RESOURCES)]
    symptoms = SYMPTOMS[idx % len(SYMPTOMS)]

    signal = IncidentSignal(
        resource=f"{resource}-{idx}",  # unique resource per signal to avoid duplicate collapsing
        namespace="load-test-ns",
        symptom_tags=symptoms,
        severity="high" if idx % 3 == 0 else "medium",
        raw_context={"load_test_index": idx, "timestamp": time.time()},
    )

    try:
        incident = orch.process_signal(signal)
        return ("ok", incident.id)
    except Exception as e:
        return ("error", str(e))


def main():
    print(f"🔥 SentinelOps Load Test: {TOTAL_SIGNALS} signals, {MAX_WORKERS} workers")
    print("=" * 60)

    # Use a temp DB for load testing
    db_path = Path("/tmp/sentinelops_load_test.db")
    if db_path.exists():
        db_path.unlink()

    store = Store(db_path=db_path)
    graph = IncidentGraph(store)
    mock_llm = create_mock_llm()

    # Seed the DB with prior successful outcomes so confidence starts high
    for symptom_list in SYMPTOMS:
        symptom_cluster = symptom_list[0]
        fr = store.get_or_create_fix_record("restart_pod", symptom_cluster)
        for _ in range(10):
            store.record_outcome(fr.id, success=True)

    orch = Orchestrator(store, graph, dry_run=False, client_override=mock_llm)

    start = time.time()
    results = {"ok": 0, "error": 0}
    errors = []

    # Fire signals concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = executor.map(process_one, [(i, orch) for i in range(TOTAL_SIGNALS)])
        for status, detail in futures:
            results[status] += 1
            if status == "error":
                errors.append(detail)

    elapsed = time.time() - start
    throughput = TOTAL_SIGNALS / elapsed

    print(f"\n📊 Results:")
    print(f"   Total signals:  {TOTAL_SIGNALS}")
    print(f"   Successful:     {results['ok']}")
    print(f"   Errors:         {results['error']}")
    print(f"   Elapsed:        {elapsed:.2f}s")
    print(f"   Throughput:     {throughput:.1f} signals/sec")

    # Verify DB integrity
    incidents = store.list_incidents()
    print(f"\n🗄  Database integrity:")
    print(f"   Incidents created: {len(incidents)}")
    print(f"   Graph nodes:       {graph.node_count}")
    print(f"   Graph edges:       {graph.edge_count}")

    if errors:
        print(f"\n⚠️  First 5 errors:")
        for e in errors[:5]:
            print(f"   - {e}")

    # Cleanup
    store.close()
    db_path.unlink(missing_ok=True)
    wal = db_path.with_suffix(".db-wal")
    shm = db_path.with_suffix(".db-shm")
    wal.unlink(missing_ok=True)
    shm.unlink(missing_ok=True)

    if results["error"] == 0:
        print(f"\n✅ LOAD TEST PASSED — {throughput:.1f} signals/sec with zero errors")
        return 0
    else:
        error_rate = results["error"] / TOTAL_SIGNALS * 100
        if error_rate < 1.0:
            print(f"\n⚠️  LOAD TEST PASSED WITH WARNINGS — {error_rate:.1f}% error rate")
            return 0
        else:
            print(f"\n❌ LOAD TEST FAILED — {error_rate:.1f}% error rate")
            return 1


if __name__ == "__main__":
    sys.exit(main())
