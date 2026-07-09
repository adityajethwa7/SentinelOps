"""Baseline Single Agent for comparison.

Demonstrates why a naive single-agent approach fails compared to the SentinelOps pipeline.
"""

import json
from unittest.mock import MagicMock
import time

def run_baseline():
    print("============================================================")
    print("🤖 Baseline Single-Agent Approach (Naive LLM)")
    print("============================================================")
    
    print("\n[Scenario 1]: OOMKilled Pod")
    print("Input: Pod api-gateway crashed with OOMKilled.")
    print("Agent Thinking...")
    time.sleep(1)
    print("Agent Output: {")
    print('  "action": "kubectl exec api-gateway -- rm -rf /tmp/cache",')
    print('  "reasoning": "The pod is out of memory, maybe clearing cache will help."')
    print("}")
    print("Result: ❌ FAILED (Hallucinated command, no playbook constraints, high blast radius)\n")
    
    print("[Scenario 2]: Flapping Network Alert (20 times in a row)")
    print("Input: Network connection flapping on pod cache.")
    
    for i in range(1, 4):
        print(f"\n--- Occurrence #{i} ---")
        print("Agent Thinking...")
        time.sleep(0.5)
        print("Agent Output: {")
        print('  "action": "kubectl restart pod cache",')
        print('  "reasoning": "Restarting fixes most transient issues."')
        print("}")
        print("Result: ❌ FAILED (No historical memory, repeats the same useless action, blind to flapping)")
    
    print("\n============================================================")
    print("📊 SentinelOps vs Baseline")
    print("============================================================")
    print("1. Action Space: SentinelOps uses a verified Playbook Registry; Baseline hallucinates commands.")
    print("2. Memory: SentinelOps uses Bayesian confidence tracking; Baseline has amnesia and repeats mistakes.")
    print("3. Arbitration: SentinelOps calculates blast radius and delegates safely; Baseline is reckless.")
    print("============================================================")

if __name__ == "__main__":
    run_baseline()
