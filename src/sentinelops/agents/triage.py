"""Triage agent (Stage B).

Extracts formalized symptom tags and severity from raw incident context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI

from sentinelops.llm.qwen_client import reason
from sentinelops.models.signal import IncidentSignal
from sentinelops.agents.protocol import TriageOutput


class TriageAgent:
    """Agent responsible for classifying an incoming incident signal."""
    
    TOOL_SCHEMA = {
        "type": "function",
        "function": {
            "name": "submit_triage_result",
            "description": "Submit the formalized triage classification for the incident.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symptom_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of standard symptom tags (e.g., 'CrashLoopBackOff', 'OOMKilled', 'HighLatency')"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Assessed severity of the incident."
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of the classification."
                    }
                },
                "required": ["symptom_tags", "severity", "reasoning"]
            }
        }
    }

    def __init__(self, client_override: Optional[OpenAI] = None):
        self.client_override = client_override

    def execute(self, signal: IncidentSignal) -> TriageOutput:
        """Triage the raw signal into structured tags and severity."""
        prompt = (
            f"Triage this incident signal.\n"
            f"Resource: {signal.resource}\n"
            f"Namespace: {signal.namespace}\n"
            f"Initial tags: {signal.symptom_tags}\n"
            f"Initial severity: {signal.severity}\n"
            f"Context: {signal.raw_context}\n\n"
            f"Analyze the context and extract standard symptom tags and the true severity."
        )

        messages = [
            {"role": "system", "content": "You are an SRE Triage Agent. Extract exact symptom tags and assess severity."},
            {"role": "user", "content": prompt}
        ]

        result = reason(
            "triage", 
            messages, 
            tools=[self.TOOL_SCHEMA],
            client_override=self.client_override
        )
        if "error" in result or "symptom_tags" not in result:
            return TriageOutput(
                symptom_tags=["unknown_symptom"],
                severity="high",
                reasoning="Fallback due to LLM parsing error."
            )
        return TriageOutput.from_dict(result)
