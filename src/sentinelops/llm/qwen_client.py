"""Qwen LLM client via Alibaba Cloud Model Studio.

Supports automatic fallback to mock responses when DASHSCOPE_API_KEY is not set,
enabling the system to run in demo/test mode without real API credentials.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI

from sentinelops.config.settings import settings

logger = logging.getLogger(__name__)

# Initialize client conditionally so tests can mock it without failing on missing keys
_client: Optional[OpenAI] = None

def _init_client() -> Optional[OpenAI]:
    """Lazily initialize the OpenAI client if API key is available."""
    global _client
    if _client is not None:
        return _client
    api_key = settings.QWEN_API_KEY or settings.DASHSCOPE_API_KEY
    if api_key:
        try:
            if settings.QWEN_API_KEY and not settings.MODELSTUDIO_WORKSPACE_ID:
                base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            else:
                base_url = settings.modelstudio_base_url
            _client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )
            logger.info("Qwen client initialized successfully with API.")
            return _client
        except Exception as e:
            logger.warning(f"Failed to initialize Qwen client: {e}")
            return None
    return None


MODELS = {
    "triage": "qwen-plus",
    "investigation": "qwen-plus",
    "planning": "qwen-plus",
    "arbitration": "qwen-max",
    "cheap": "qwen-turbo",
}


class MockFallbackClient:
    """Provides deterministic mock LLM responses when no API key is available.

    This enables the full agent pipeline to run in demo/test mode without
    requiring real Qwen API credentials. The responses are sensible defaults
    that exercise all code paths.
    """

    MOCK_RESPONSES = {
        "Triage": {
            "symptom_tags": ["unknown_symptom"],
            "severity": "high",
            "reasoning": "Mock triage: defaulting to high severity for safety.",
        },
        "Investigator": {
            "cause": "Unknown (mock mode)",
            "p_diagnosis": 0.5,
            "evidence": {"note": "Running in mock LLM mode — no real diagnosis."},
        },
        "Planner": {
            "action": "restart_pod",
            "params": {"namespace": "default", "pod_name": "unknown"},
            "blast_radius": "low",
        },
    }

    def detect_agent(self, messages: List[Dict[str, str]]) -> str:
        """Detect which agent is calling based on the system prompt."""
        sys_prompt = messages[0].get("content", "") if messages else ""
        for key in self.MOCK_RESPONSES:
            if key in sys_prompt:
                return key
        return "Triage"

    def create_mock_response(self, agent_key: str) -> Dict[str, Any]:
        """Create a mock response dict for the given agent."""
        return self.MOCK_RESPONSES.get(agent_key, self.MOCK_RESPONSES["Triage"])


_mock_fallback = MockFallbackClient()


def reason(
    model_key: str,
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
    client_override: Optional[OpenAI] = None,
) -> Dict[str, Any]:
    """Execute a reasoning call against Qwen with automatic mock fallback.

    Args:
        model_key: Key matching a model in MODELS dict.
        messages: Standard OpenAI-style messages list.
        tools: Optional list of tools (functions) for structured output.
        client_override: Optional mock client for testing.

    Returns:
        The tool call arguments as a parsed JSON dict, or plain text if no tool was called.
        Falls back to mock responses if no API client is available.
    """
    c = client_override or _init_client()

    if not c:
        # Graceful fallback to mock responses
        agent_key = _mock_fallback.detect_agent(messages)
        mock_response = _mock_fallback.create_mock_response(agent_key)
        logger.debug(f"Using mock fallback for {agent_key} (no API key configured)")
        return mock_response

    # Real API call
    try:
        response = c.chat.completions.create(
            model=MODELS[model_key],
            messages=messages,
            tools=tools,
            temperature=0.2,
        )
    except Exception as e:
        # On API error, fall back to mock
        logger.warning(f"Qwen API call failed ({e}), falling back to mock response")
        agent_key = _mock_fallback.detect_agent(messages)
        return _mock_fallback.create_mock_response(agent_key)

    choice = response.choices[0]

    if choice.message.tool_calls:
        # Extract the first tool call arguments
        tool_call = choice.message.tool_calls[0]
        try:
            return json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return {
                "error": "Failed to parse tool call arguments",
                "raw": tool_call.function.arguments,
            }

    return {"text": choice.message.content or ""}


# Backward compatibility: expose `client` at module level for existing code
client = _init_client()
