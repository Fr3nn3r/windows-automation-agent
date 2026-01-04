"""
Router - Atomic Executor for the Windows Automation Agent.

Maps Intent -> Tool -> Result.
No loops. No retries. Fail fast.

Design philosophy: "Stateful Context, Atomic Action"
- User acts as the "Orchestrator"
- Agent acts as the "Bionic Arm"
"""

import time
import uuid
from typing import Dict, Any, Optional

from core.protocols import DecisionMaker, ToolExecutor
from core.context import AgentContext
from core.constants import LATENCY_TOOLS
from core.tool_decorator import get_destructive_tools


class Router:
    """
    Atomic Executor - maps Intent -> Tool -> Result.
    No loops. No retries. Fail fast.

    Implements the StateManager protocol.
    """

    def __init__(self, brain: DecisionMaker, body: ToolExecutor):
        """
        Initialize the Router.

        Args:
            brain: Decision maker implementing DecisionMaker protocol
            body: Tool executor implementing ToolExecutor protocol
        """
        self.brain = brain
        self.body = body
        self.context: Optional[AgentContext] = None

    def start_session(self) -> str:
        """
        Initialize a new session with fresh context.

        Returns:
            The new session ID
        """
        session_id = str(uuid.uuid4())[:8]
        self.context = AgentContext(session_id=session_id)
        return session_id

    def end_session(self) -> None:
        """Clean up session state."""
        self.context = None

    def _confirm_destructive_action(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """
        Intercept destructive actions and prompt user for confirmation.

        Args:
            tool_name: The name of the tool to execute
            args: The arguments for the tool

        Returns:
            True if user confirms or action is not destructive, False otherwise
        """
        # Get destructive tools dynamically from the tool specs
        destructive_actions = get_destructive_tools()

        if tool_name not in destructive_actions:
            return True  # Non-destructive, proceed

        config = destructive_actions[tool_name]
        target = args.get(config["target_key"], str(args))

        print(f"\n{'='*50}")
        print(f"[SAFETY - {config['risk']} RISK] Destructive action requested:")
        print(f"  Action: {config['message']}")
        print(f"  Target: {target}")
        print(f"{'='*50}")

        response = input("Type 'yes' to confirm: ").strip().lower()
        return response == "yes"

    def _sanitize_output(self, result: Dict[str, Any], max_items: int = 50) -> Dict[str, Any]:
        """
        Truncate large results to prevent context flooding.

        Args:
            result: The raw tool result
            max_items: Maximum number of items to keep in lists

        Returns:
            Sanitized result dict
        """
        for key in ["items", "processes", "windows"]:
            if key in result and isinstance(result[key], list):
                items = result[key]
                if len(items) > max_items:
                    result[key] = items[:max_items]
                    result["truncated"] = True
                    result["total_count"] = len(items)

        return result

    def process(self, user_input: str) -> Dict[str, Any]:
        """
        Atomic Execution: Input -> LLM -> Tool -> Result.
        No loops. No retries. Fail fast.

        Args:
            user_input: The user's command/request

        Returns:
            Result dict with 'status' and other tool-specific data
        """
        if not self.context:
            self.start_session()

        # 1. Refresh Context (Only what's needed for THIS decision)
        self.context.refresh_environment(self.body.windows if hasattr(self.body, 'windows') else None)
        self.context.add_turn("user", user_input)

        # 2. DECIDE (Router/Brain) - Single pass
        decision = self.brain.decide(self.context, user_input)

        # 3. VALIDATE - Handle list by taking first action only
        if isinstance(decision, list):
            if not decision:
                return {"status": "error", "message": "Empty action list"}
            # Atomic: take first action only, warn if more
            if len(decision) > 1:
                print(f"[ATOMIC] LLM returned {len(decision)} actions, executing first only.")
            decision = decision[0]

        tool_name = decision.get("tool")
        args = decision.get("args", {})

        # Handle error from Brain
        if tool_name == "error":
            error_msg = args.get("message", "Unknown error")
            return {"status": "error", "message": error_msg}

        # 4. CONFIRM (if destructive)
        if not self._confirm_destructive_action(tool_name, args):
            return {"status": "cancelled", "message": f"User cancelled {tool_name}"}

        # 5. ACT (Body) - No retry, fail fast
        func = self.body.get(tool_name)
        if not func:
            return {"status": "error", "message": f"Tool '{tool_name}' not found"}

        try:
            result = func(**args)
            result = self._sanitize_output(result)

            # 6. UPDATE STATE (for HUD)
            self.context.update_state(result)

            # Latency injection: wait for UI after certain tools
            if tool_name in LATENCY_TOOLS and result.get("status") == "success":
                delay = LATENCY_TOOLS[tool_name]
                time.sleep(delay)

            # Record in short-term history
            self.context.add_turn(
                "tool_result",
                str(result),
                tool_name=tool_name,
                tool_args=args,
                tool_result=result
            )

            return result

        except TypeError as e:
            return {"status": "error", "message": f"Argument mismatch for {tool_name}: {e}"}
        except Exception as e:
            return {"status": "error", "message": f"{tool_name} failed: {e}"}
