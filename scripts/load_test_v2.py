#!/usr/bin/env python3
"""Enhanced load test: 5000 concurrent signals, 50 workers, latency percentiles.

Usage:
    uv run python scripts/load_test_v2.py
"""

import concurrent.futures
import json
import time
import statistics
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path
from unittest.mock import MagicMock
from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph
from sentinelops.models.signal import IncidentSignal
from sentinelops.orchestrator import Orchestrator

TOTAL_SIGNALS = 5000
MAX_WORKERS = 50

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

BASELINE_THROUGHPUT = 30.0


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


def process_one(args):
    idx, orch = args
    resource = RESOURCES[idx % len(RESOURCES)]
    symptoms = SYMPTOMS[idx % len(SYMPTOMS)]

    signal = IncidentSignal(
        resource=f"{resource}-{idx}",
        namespace="load-test-ns",
        symptom_tags=symptoms,
        severity="high" if idx % 3 == 0 else "medium",
        raw_context={"load_test_index": idx, "timestamp": time.time()},
    )

    t0 = time.perf_counter()
    try:
        incident = orch.process_signal(signal)
        latency = (time.perf_counter() - t0) * 1000
        return ("ok", incident.id, latency)
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return ("error", str(e), latency)


def main():
    print(f" SentinelOps Enhanced Load Test: {TOTAL_SIGNALS} signals, {MAX_WORKERS} workers")
    print("=" * 60)

    db_path = Path("/tmp/sentinelops_load_test_v2.db")
    if db_path.exists():
        db_path.unlink()

    store = Store(db_path=db_path)
    graph = IncidentGraph(store)
    mock_llm = create_mock_llm()

    for symptom_list in SYMPTOMS:
        symptom_cluster = symptom_list[0]
        fr = store.get_or_create_fix_record("restart_pod", symptom_cluster)
        for _ in range(10):
            store.record_outcome(fr.id, success=True)

    orch = Orchestrator(store, graph, dry_run=False, client_override=mock_llm)

    try:
        import psutil
        proc = psutil.Process()
        mem_before = proc.memory_info().rss / (1024 * 1024)
    except ImportError:
        mem_before = 0.0

    start = time.time()
    results = {"ok": 0, "error": 0}
    errors = []
    latencies = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = executor.map(process_one, [(i, orch) for i in range(TOTAL_SIGNALS)])
        for status, detail, latency in futures:
            results[status] += 1
            latencies.append(latency)
            if status == "error":
                errors.append(detail)

    elapsed = time.time() - start
    throughput = TOTAL_SIGNALS / elapsed

    try:
        import psutil
        mem_after = proc.memory_info().rss / (1024 * 1024)
        mem_growth = mem_after - mem_before
    except ImportError:
        mem_after = mem_growth = 0.0

    sorted_lat = sorted(latencies)
    p50 = statistics.median(sorted_lat) if sorted_lat else 0
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0
    p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0

    print(f"\n Results:")
    print(f"   Total signals:   {TOTAL_SIGNALS}")
    print(f"   Successful:      {results['ok']}")
    print(f"   Errors:          {results['error']}")
    print(f"   Elapsed:         {elapsed:.2f}s")
    print(f"   Throughput:      {throughput:.1f} signals/sec")
    print(f"   Latency P50:     {p50:.1f}ms")
    print(f"   Latency P95:     {p95:.1f}ms")
    print(f"   Latency P99:     {p99:.1f}ms")
    print(f"   Memory Before:   {mem_before:.1f}MB")
    print(f"   Memory After:    {mem_after:.1f}MB")
    print(f"   Memory Growth:   {mem_growth:.1f}MB")

    incidents = store.list_incidents()
    print(f"\n Database integrity:")
    print(f"   Incidents:       {len(incidents)}")
    print(f"   Graph nodes:     {graph.node_count}")
    print(f"   Graph edges:     {graph.edge_count}")

    if errors:
        print(f"\n First 5 errors:")
        for e in errors[:5]:
            print(f"   - {e}")

    store.close()
    db_path.unlink(missing_ok=True)
    for suffix in [".db-wal", ".db-shm"]:
        db_path.with_suffix(suffix).unlink(missing_ok=True)

    pass_fail = True
    if results["error"] > 0:
        error_rate = results["error"] / TOTAL_SIGNALS * 100
        if error_rate >= 1.0:
            print(f"\n LOAD TEST FAILED — {error_rate:.1f}% error rate")
            pass_fail = False

    if throughput < BASELINE_THROUGHPUT:
        print(f"\n LOAD TEST FAILED — throughput {throughput:.1f} below baseline {BASELINE_THROUGHPUT}")
        pass_fail = False

    if pass_fail:
        print(f"\n LOAD TEST PASSED — {throughput:.1f} signals/sec, {results['error']} errors")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
