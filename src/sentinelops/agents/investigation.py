"""Investigation agent (Stage C).

Proposes root-cause hypotheses based on triaged incident data.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from openai import OpenAI

from sentinelops.llm.qwen_client import reason
from sentinelops.models.incident import Incident
from sentinelops.agents.protocol import InvestigationOutput, TriageOutput


class InvestigationAgent:
    """Agent responsible for proposing the most likely root cause."""
    
    TOOL_SCHEMA = {
        "type": "function",
        "function": {
            "name": "submit_hypothesis",
            "description": "Submit a hypothesis for the root cause of the incident.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cause": {
                        "type": "string",
                        "description": "The proposed root cause (e.g. 'OOMKilled due to memory limit 128Mi')."
                    },
                    "p_diagnosis": {
                        "type": "number",
                        "description": "Estimated probability (0.0 to 1.0) that this diagnosis is correct."
                    },
                    "evidence": {
                        "type": "object",
                        "description": "Key pieces of evidence supporting this hypothesis."
                    }
                },
                "required": ["cause", "p_diagnosis", "evidence"]
            }
        }
    }

    def __init__(self, client_override: Optional[OpenAI] = None):
        self.client_override = client_override

    def execute(self, incident: Incident, triage_output: Optional[TriageOutput] = None) -> InvestigationOutput:
        """Generate a root-cause hypothesis."""
        triage_info = ""
        if triage_output:
            triage_info = f"\nTriage reasoning: {triage_output.reasoning}\nTriage severity: {triage_output.severity}"
        prompt = (
            f"Investigate this incident.\n"
            f"Resource: {incident.resource}\n"
            f"Symptom tags: {incident.symptom_tags}\n"
            f"Context: {incident.raw_context}\n"
            f"{triage_info}\n\n"
            f"Provide the most likely root cause hypothesis, your confidence in the diagnosis (0.0-1.0), and the supporting evidence."
        )

        messages = [
            {"role": "system", "content": "You are a Senior K8s SRE Investigator. Diagnose the root cause."},
            {"role": "user", "content": prompt}
        ]

        result = reason(
            "investigation", 
            messages, 
            tools=[self.TOOL_SCHEMA],
            client_override=self.client_override
        )
        if "error" in result or "cause" not in result:
            return InvestigationOutput(
                cause="Unknown",
                p_diagnosis=0.0,
                evidence={"error": "Fallback due to LLM parsing error."}
            )
        return InvestigationOutput.from_dict(result)
