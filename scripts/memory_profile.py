#!/usr/bin/env python3
import sys
import os
import time
import resource
import concurrent.futures
import json
from pathlib import Path
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph
from sentinelops.models.signal import IncidentSignal
from sentinelops.orchestrator import Orchestrator

TOTAL_SIGNALS = 500
MAX_WORKERS = 2

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
    import gc
    idx, orch = args
    resource_name = RESOURCES[idx % len(RESOURCES)]
    symptoms = SYMPTOMS[idx % len(SYMPTOMS)]

    signal = IncidentSignal(
        resource=f"{resource_name}-{idx}",
        namespace="mem-test-ns",
        symptom_tags=symptoms,
        severity="high" if idx % 3 == 0 else "medium",
        raw_context={"mem_test_index": idx, "timestamp": time.time()},
    )
    orch.process_signal(signal)
    if idx % 50 == 0:
        gc.collect()

def get_peak_rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    maxrss = usage.ru_maxrss
    if sys.platform == 'darwin':
        return maxrss / (1024 * 1024)
    else:
        return maxrss / 1024

def main():
    print(f"🧠 SentinelOps Memory Profiler: {TOTAL_SIGNALS} signals under sustained load")
    print("=" * 60)

    db_path = Path("/tmp/sentinelops_mem_profile.db")
    if db_path.exists():
        db_path.unlink()

    store = Store(db_path=db_path)
    graph = IncidentGraph(store)
    mock_llm = create_mock_llm()

    # Seed the DB so actions get auto-approved
    for symptom_list in SYMPTOMS:
        symptom_cluster = symptom_list[0]
        fr = store.get_or_create_fix_record("restart_pod", symptom_cluster)
        for _ in range(10):
            store.record_outcome(fr.id, success=True)

    orch = Orchestrator(store, graph, dry_run=False, client_override=mock_llm)

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(process_one, [(i, orch) for i in range(TOTAL_SIGNALS)]))

    elapsed = time.time() - start
    peak_rss = get_peak_rss_mb()
    print(f"📊 Memory Profile Results:")
    print(f"   Peak RSS:         {peak_rss:.2f} MB")
    print(f"   Time Elapsed:     {elapsed:.2f}s")
    print(f"   Signals/sec:      {TOTAL_SIGNALS / elapsed:.1f}")
    
    store.close()
    db_path.unlink(missing_ok=True)
    for suffix in [".db-wal", ".db-shm"]:
        db_path.with_suffix(suffix).unlink(missing_ok=True)

    if peak_rss < 200.0:
        print(f"✅ MEMORY PROFILE PASSED: Peak RSS {peak_rss:.2f}MB is below 200MB threshold.")
        return 0
    else:
        print(f"❌ MEMORY PROFILE FAILED: Peak RSS {peak_rss:.2f}MB exceeds 200MB threshold.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
