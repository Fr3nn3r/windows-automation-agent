"""
Brain - The Decision Maker for the Windows Automation Agent.

Takes context + query, outputs JSON decision.
Implements the DecisionMaker protocol.
"""

import json
from typing import Dict, Any, Optional

from core.protocols import LLMClient
from core.context import AgentContext
from core.prompt_builder import build_tools_prompt


class Brain:
    """
    Atomic Decision Maker - uses LLM to map user intent to tool selection.

    Takes context + query, outputs JSON decision in the format:
    {"tool": "tool_name", "args": {...}}
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize the Brain.

        Args:
            llm_client: LLM client implementing the LLMClient protocol
        """
        self.llm_client = llm_client

    def _build_system_prompt(self, context: AgentContext) -> str:
        """Build system prompt with HUD for atomic execution."""
        # Dynamically generated tool specs from the registry
        tools_spec = build_tools_prompt()

        # Get HUD from context
        hud = context.get_hud()

        return (
            "You are a Windows Automation Router.\n"
            f"{tools_spec}\n"
            f"{hud}\n\n"
            "OUTPUT RULES:\n"
            "1. Return EXACTLY ONE JSON object: {\"tool\": \"...\", \"args\": {...}}\n"
            "2. Do NOT return a list of actions.\n"
            "3. Do NOT chain actions. If user asks for two things, pick the FIRST one.\n"
            "4. Use 'Last Action' to resolve references like 'close it', 'type here', 'that window'.\n"
            "5. Use 'Active Focus' to know which window will receive type_text.\n"
            "6. If impossible, output: {\"tool\": \"error\", \"args\": {\"message\": \"reason\"}}\n"
        )

    def decide(self, context: AgentContext, user_input: str) -> Dict[str, Any]:
        """
        Make a single atomic decision based on context and input.

        Args:
            context: Current agent context with HUD state
            user_input: The user's command/request

        Returns:
            Decision dict: {"tool": "tool_name", "args": {...}}
            Or error: {"tool": "error", "args": {"message": "reason"}}
        """
        try:
            # Build messages with history
            messages = [
                {"role": "system", "content": self._build_system_prompt(context)}
            ]
            messages.extend(context.get_history_for_prompt())

            # Add current request if not already the last message
            if not context.short_term_history or context.short_term_history[-1].content != user_input:
                messages.append({"role": "user", "content": user_input})

            # Call LLM
            response_text = self.llm_client.complete(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
            )

            print(f"[Brain] Decision: {response_text}")
            return json.loads(response_text)

        except json.JSONDecodeError as e:
            return {"tool": "error", "args": {"message": f"Invalid JSON from LLM: {e}"}}
        except Exception as e:
            return {"tool": "error", "args": {"message": f"LLM failure: {e}"}}
