"""Ingests a CSV of historical incidents into the Bayesian Memory Graph.

This allows SentinelOps to achieve "Day 1 Trust" by learning from past 
successful human remediations (e.g. from PagerDuty or ServiceNow exports)
before seeing its first live alert.
"""

import csv
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph
from sentinelops.memory.confidence import action_confidence

def ingest_historical_data(csv_path: str):
    print("============================================================")
    print("📈 SentinelOps: Historical Data Harness")
    print("============================================================")
    
    db_path = Path("data/sentinelops.db")
    store = Store(db_path)
    graph = IncidentGraph(store)
    
    print(f"Reading from {csv_path}...")
    
    success_count = 0
    with open(csv_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            resource = row['resource']
            symptom = row['symptom']
            action = row['action_taken']
            success = bool(int(row['success']))
            occurred_at = datetime.fromisoformat(row['timestamp'].replace("Z", ""))
            
            # 1. Create or get fix record
            fr = store.get_or_create_fix_record(action, symptom)
            
            # 2. Record outcome
            store.record_outcome(fr.id, success, occurred_at)
            
            # 3. Link graph edge
            fingerprint = f"{resource}-{symptom}"
            graph.link(fingerprint, fr.id, weight=1.0)
            
            success_count += 1
            
    print(f"✅ Ingested {success_count} historical records into memory graph.")
    print("============================================================")
    
    # Calculate day-1 confidence for our key test case
    test_fr = store.get_or_create_fix_record("restart_pod", "OOMKilled")
    outcomes = test_fr.outcome_tuples()
    # Assuming the LLM diagnosis probability is roughly 1.0 for obvious OOMKilled
    conf = action_confidence(1.0, outcomes)
    
    print("\n📊 Day-1 Trust Metrics:")
    print(f"Action: restart_pod | Cluster: OOMKilled")
    print(f"Initial Starting Confidence: 19.6%")
    print(f"Day-1 Loaded Confidence: {conf * 100:.1f}%")
    
    if conf >= 0.85:
        print("⚡ AUTONOMOUS REMEDIATION BARRIER REACHED on Day 1.")
    else:
        print("🤖 Still requires Human-in-the-Loop.")
        
    print("============================================================")

if __name__ == "__main__":
    csv_file = Path("data/historical_incidents.csv")
    if csv_file.exists():
        ingest_historical_data(str(csv_file))
    else:
        print(f"Error: {csv_file} not found.")
