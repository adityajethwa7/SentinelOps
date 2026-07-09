#!/usr/bin/env python3
"""Enhanced memory profiler with tracemalloc, per-phase timing, and JSON report.

Usage:
    uv run python scripts/memory_profile_v2.py --signals 1000
"""

import argparse
import gc
import json
import os
import resource
import sys
import time
import tracemalloc
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph
from sentinelops.models.signal import IncidentSignal
from sentinelops.orchestrator import Orchestrator

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


def get_peak_rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    maxrss = usage.ru_maxrss
    if sys.platform == "darwin":
        return maxrss / (1024 * 1024)
    return maxrss / 1024


def create_mock_llm():
    mock_client = MagicMock()
    triage_args = json.dumps({
        "symptom_tags": ["CrashLoopBackOff"],
        "severity": "high",
        "reasoning": "Symptom detected",
    })
    inv_args = json.dumps({
        "cause": "Memory Leak",
        "p_diagnosis": 0.9,
        "evidence": {"log": "OOM killed"},
    })
    plan_args = json.dumps({
        "action": "restart_pod",
        "params": {"namespace": "default", "pod_name": "test-pod"},
        "blast_radius": "low",
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


def main():
    parser = argparse.ArgumentParser(description="SentinelOps Enhanced Memory Profiler")
    parser.add_argument("--signals", type=int, default=1000, help="Number of signals to process")
    args = parser.parse_args()

    total_signals = args.signals
    print(f" SentinelOps Enhanced Memory Profiler: {total_signals} signals")
    print("=" * 60)

    db_path = Path("/tmp/sentinelops_mem_profile_v2.db")
    if db_path.exists():
        db_path.unlink()

    os.environ["SENTINELOPS_MEMORY_PROFILING"] = "1"

    tracemalloc.start()
    gc.collect()
    snapshot_before = tracemalloc.take_snapshot()

    phase_times = {}
    t_start = time.time()

    store = Store(db_path=db_path)
    graph = IncidentGraph(store)
    mock_llm = create_mock_llm()

    for symptom_list in SYMPTOMS:
        symptom_cluster = symptom_list[0]
        fr = store.get_or_create_fix_record("restart_pod", symptom_cluster)
        for _ in range(10):
            store.record_outcome(fr.id, success=True)

    orch = Orchestrator(store, graph, dry_run=False, client_override=mock_llm)
    t_ingestion_end = time.time()
    phase_times["ingestion"] = t_ingestion_end - t_start

    t_process_start = time.time()
    for i in range(total_signals):
        resource_name = RESOURCES[i % len(RESOURCES)]
        symptoms = SYMPTOMS[i % len(SYMPTOMS)]

        signal = IncidentSignal(
            resource=f"{resource_name}-{i}",
            namespace="mem-test-ns",
            symptom_tags=symptoms,
            severity="high" if i % 3 == 0 else "medium",
            raw_context={"mem_test_index": i, "timestamp": time.time()},
        )
        orch.process_signal(signal)

        if i % 50 == 0:
            gc.collect()
    t_process_end = time.time()
    phase_times["processing"] = t_process_end - t_process_start

    gc.collect()
    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    elapsed = t_process_end - t_start
    peak_rss = get_peak_rss_mb()

    top_allocations = []
    for stat in stats[:10]:
        top_allocations.append({
            "file": str(stat.traceback[0].filename) if stat.traceback else "<unknown>",
            "line": stat.traceback[0].lineno if stat.traceback else 0,
            "size_bytes": stat.size_diff,
            "count": stat.count_diff,
        })

    current, peak = tracemalloc.get_traced_memory()
    report = {
        "peak_rss_mb": round(peak_rss, 2),
        "peak_python_heap_mb": round(peak / (1024 * 1024), 2),
        "total_signals": total_signals,
        "elapsed_seconds": round(elapsed, 2),
        "signals_per_second": round(total_signals / elapsed, 1),
        "phase_times": {k: round(v, 4) for k, v in phase_times.items()},
        "per_signal_cost_ms": round(elapsed / total_signals * 1000, 2),
        "graph_nodes": graph.node_count,
        "graph_edges": graph.edge_count,
        "store_incidents": len(store.list_incidents()),
        "top_10_allocations": top_allocations,
    }

    # Print report
    print(f"\n Memory Profile Results:")
    print(f"   Peak RSS:              {report['peak_rss_mb']} MB")
    print(f"   Peak Python Heap:      {report['peak_python_heap_mb']} MB")
    print(f"   Time Elapsed:          {report['elapsed_seconds']}s")
    print(f"   Signals/sec:           {report['signals_per_second']}")
    print(f"   Per-signal cost:       {report['per_signal_cost_ms']}ms")
    print(f"   Graph nodes/edges:     {report['graph_nodes']} / {report['graph_edges']}")
    print(f"   Incidents in store:    {report['store_incidents']}")
    print(f"\n Phase Times:")
    for phase, dur in phase_times.items():
        print(f"   {phase}: {dur:.4f}s")
    print(f"\n Top 10 Allocation Sources:")
    for a in top_allocations:
        print(f"   {a['file']}:{a['line']}  +{a['size_bytes']/1024:.1f}KB ({a['count']} blocks)")

    # Save JSON report
    out_dir = Path("scripts/profiles")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"profile_{total_signals}_signals.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n Report saved to {report_path}")

    store.close()
    db_path.unlink(missing_ok=True)
    for suffix in [".db-wal", ".db-shm"]:
        db_path.with_suffix(suffix).unlink(missing_ok=True)

    del os.environ["SENTINELOPS_MEMORY_PROFILING"]

    threshold = 250
    if peak_rss < threshold:
        print(f"\n MEMORY PROFILE PASSED: Peak RSS {peak_rss:.2f}MB is below {threshold}MB threshold.")
        return 0
    else:
        print(f"\n MEMORY PROFILE FAILED: Peak RSS {peak_rss:.2f}MB exceeds {threshold}MB threshold.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
