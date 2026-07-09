import pytest
import json
from unittest.mock import MagicMock, patch
from sentinelops.llm.qwen_client import reason, _init_client

def test_qwen_client_init_none():
    with patch("sentinelops.llm.qwen_client.settings") as mock_settings:
        mock_settings.QWEN_API_KEY = ""
        mock_settings.DASHSCOPE_API_KEY = ""
        with patch("sentinelops.llm.qwen_client._client", None):
            res = _init_client()
            assert res is None

def test_reason_api_error_fallback():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API Error")
    
    messages = [{"role": "system", "content": "You are a Triage agent."}]
    res = reason("triage", messages, client_override=mock_client)
    assert res["severity"] == "high"

def test_reason_non_tool_call():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.tool_calls = None
    mock_choice.message.content = "Plain text response"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    
    messages = [{"role": "user", "content": "hello"}]
    res = reason("triage", messages, client_override=mock_client)
    assert res == {"text": "Plain text response"}

def test_reason_json_decode_error():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.function.arguments = "{invalid json"
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    
    messages = [{"role": "user", "content": "hello"}]
    res = reason("triage", messages, client_override=mock_client)
    assert "error" in res
    assert res["raw"] == "{invalid json"
