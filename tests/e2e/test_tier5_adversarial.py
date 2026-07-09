import pytest
import asyncio
import random
import time
from concurrent.futures import ThreadPoolExecutor

def test_tier5_adversarial_chaos_monkey(client):
    """Bombard the API with conflicting signals and malformed payloads to break SQLite locks."""
    headers = {"X-API-Key": "sentinelops-hackathon-2026"}
    
    def send_chaotic_signal(i):
        # 10% chance of malformed payload
        if random.random() < 0.1:
            payload = {"namespace": "default"} # Missing resource
        else:
            payload = {
                "resource": f"pod/chaos-target-{i % 5}", # Induce duplication and collapsing
                "namespace": "default",
                "raw_context": {"alertname": "OOMKilled", "chaos_entropy": random.random()}
            }
        
        # Fire request
        resp = client.post("/api/signals", json=payload, headers=headers)
        return resp.status_code

    start_time = time.time()
    
    # Run 100 concurrent requests
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(send_chaotic_signal, range(100)))
        
    duration = time.time() - start_time
    
    # Count results
    success_200 = results.count(200)
    failed_422 = results.count(422)
    server_errors = [r for r in results if r >= 500]
    
    # Assertions
    assert len(server_errors) == 0, f"Found 500 internal server errors during chaos monkey: {server_errors}"
    assert duration < 10.0, f"Chaos monkey took too long: {duration}s"
    
    # Verify DB consistency
    feed_resp = client.get("/api/incidents")
    assert feed_resp.status_code == 200
    
    # We expect at most 5 incidents because we only target 5 resources (due to duplication collapsing)
    # The actual number might be less if some were malformed.
    incidents = feed_resp.json()
    chaos_incidents = [i for i in incidents if i["resource"].startswith("pod/chaos-target-")]
    
    assert len(chaos_incidents) <= 5, "Duplicate collapsing failed under concurrent load!"
