import pytest
import sqlite3
import tracemalloc
import time
from uuid import uuid4
from sentinelops.memory.store import Store, DEFAULT_DB_PATH
from sentinelops.models.incident import Incident

@pytest.fixture
def clean_store():
    store = Store(":memory:") # Use in-memory for speed but test schema limits
    yield store
    store.close()

def test_1000_signals_load_and_memory(clean_store):
    """Stress test memory and SQLite insertions for 1000 concurrent-like signals."""
    tracemalloc.start()
    
    start_time = time.time()
    
    # Simulate 1000 rapid signal ingestions
    for i in range(1000):
        inc = Incident(
            fingerprint=f"pod-crash-{i}",
            resource=f"pod/test-{i}",
            namespace="default",
            symptom_tags=["CrashLoopBackOff"],
            severity="high",
            raw_context={"alert": "yes"}
        )
        clean_store.create_incident(inc)
        
    end_time = time.time()
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Assertions
    # 1. 1000 records successfully saved
    assert len(clean_store.list_incidents()) == 1000
    
    # 2. Timing < 5 seconds for 1000 SQLite inserts using WAL + NORMAL
    duration = end_time - start_time
    assert duration < 5.0, f"Insertions took too long: {duration}s"
    
    # 3. Memory overhead is strictly under 50MB (50 * 1024 * 1024 bytes)
    assert peak < 50 * 1024 * 1024, f"Memory footprint exceeded 50MB: {peak / 1024 / 1024:.2f}MB"
