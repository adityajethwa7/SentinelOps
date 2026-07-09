"""Planning agent (Stage D).

Selects a remediation action from the playbook registry based on the hypothesis.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from openai import OpenAI

from sentinelops.llm.qwen_client import reason
from sentinelops.models.incident import Hypothesis, Incident
from sentinelops.playbooks.registry import registry
from sentinelops.agents.protocol import PlanningOutput, InvestigationOutput


class PlanningAgent:
    """Agent responsible for selecting an action and providing parameters."""
    
    TOOL_SCHEMA = {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "Submit a remediation plan using an action from the registry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "The exact name of the playbook action to execute."
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters required for the action."
                    },
                    "blast_radius": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Estimated blast radius / risk of this action."
                    }
                },
                "required": ["action", "params", "blast_radius"]
            }
        }
    }

    def __init__(self, client_override: Optional[OpenAI] = None):
        self.client_override = client_override

    def execute(self, incident: Incident, hypothesis: Hypothesis | InvestigationOutput) -> PlanningOutput:
        """Generate a remediation plan."""
        
        # Inject available actions into the prompt
        available_actions = json.dumps(registry.list_actions(), indent=2)
        
        prompt = (
            f"Plan a remediation for this incident.\n"
            f"Resource: {incident.resource}\n"
            f"Symptoms: {incident.symptom_tags}\n"
            f"Hypothesis: {hypothesis.cause} (confidence: {hypothesis.p_diagnosis})\n\n"
            f"Available Playbook Actions:\n{available_actions}\n\n"
            f"Select the appropriate action, provide its required parameters, and assess the blast radius."
        )

        messages = [
            {"role": "system", "content": "You are a Kubernetes Remediation Planner. Only use actions from the provided registry."},
            {"role": "user", "content": prompt}
        ]

        result = reason(
            "planning", 
            messages, 
            tools=[self.TOOL_SCHEMA],
            client_override=self.client_override
        )
        if "error" in result or "action" not in result:
            return PlanningOutput(
                action="unknown",
                params={},
                blast_radius="high"
            )
        return PlanningOutput.from_dict(result)
