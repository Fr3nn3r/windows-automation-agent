"""
Brain - The Decision Maker for the Windows Automation Agent.

Takes context + query, outputs JSON decision.
Implements the DecisionMaker protocol.
"""

import json
from typing import Dict, Any, Optional

from core.protocols import LLMClient
from core.context import AgentContext


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
        tools_spec = """
Tools and their EXACT argument names:
- set_brightness: args: {"level": <int 0-100|}
- turn_screen_off: args: {}
- turn_screen_on: args: {}
- list_windows: args: {} -> Returns numbered list like "1. Notepad", "2. Chrome". Use IDs for other commands.
- focus_window: args: {"window_id": <int or string|}
- minimize_window: args: {"window_id": <int or string|}
- maximize_window: args: {"window_id": <int or string|}
- minimize_all: args: {"filter_name": "<optional>"|}
- restore_all: args: {}
- close_window: args: {"window_id": <int or string|}  [DESTRUCTIVE]
- list_desktops: args: {}
- switch_desktop: args: {"index": <int|}
- move_window: args: {"window_id": <int or string>, "desktop_index": <int|}
- list_files: args: {"path": "<directory path>|}
- get_sys_info: args: {}
- check_processes: args: {"filter_name": "<optional>"|} or {}
- delete_item: args: {"path": "<path>", "confirm": true|}  [DESTRUCTIVE]
- launch_app: args: {"app_name": "<app name like 'notepad', 'chrome'>|}
- open_explorer: args: {"path": "<folder path>|}
- get_clipboard: args: {}
- set_clipboard: args: {"text": "<text>|}
- type_text: args: {"text": "<text>"|}
- get_env: args: {"var_name": "<env var name like 'PATH'>|}
- list_usb: args: {}
- change_dir: args: {"path": "<directory path>|}
"""

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
