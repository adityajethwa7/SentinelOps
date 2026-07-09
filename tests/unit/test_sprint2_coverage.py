"""Unit tests for coverage gaps found in Sprint 2."""

import pytest
from sentinelops.memory.store import Store
from sentinelops.memory.confidence import action_confidence
from sentinelops.llm.qwen_client import reason

def test_store_fix_records(tmp_path):
    db_file = tmp_path / "test.db"
    store = Store(db_path=db_file)
    store.get_or_create_fix_record("restart_pod", "OOMKilled")
    fr = store.get_or_create_fix_record("restart_pod", "OOMKilled")
    store.record_outcome(fr.id, True)
    
    records = store.list_fix_records()
    assert len(records) == 1
    assert records[0].action == "restart_pod"
    
    record = store.get_fix_record(fr.id)
    assert record is not None
    assert record.id == fr.id
    
    store.close()

def test_confidence_zero_outcomes():
    # Line 86 in confidence.py handles outcomes == 0, let's hit it with valid params
    from datetime import datetime
    from sentinelops.models.fix_record import FixOutcome
    
    # Prior A=1, B=1, no outcomes
    conf = action_confidence(1.0, [])
    assert conf > 0.0

def test_qwen_client_error_handling():
    # Test JSON decode error
    messages = [{"role": "user", "content": "hi"}]
    
    class MockToolFunction:
        arguments = "invalid json"
        
    class MockToolCall:
        function = MockToolFunction()
        
    class MockMessage:
        tool_calls = [MockToolCall()]
        content = ""
        
    class MockChoice:
        message = MockMessage()
        
    class MockResponse:
        choices = [MockChoice()]
        
    class MockCreate:
        def create(self, **kwargs):
            return MockResponse()
            
    class MockChat:
        completions = MockCreate()
        
    class MockClient:
        chat = MockChat()
        
    # Inject mock client for reason
    res = reason("triage", messages, client_override=MockClient())
    assert "error" in res
    assert res["error"] == "Failed to parse tool call arguments"
