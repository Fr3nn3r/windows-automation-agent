"""
LocalAgent - High-level facade for the Windows Automation Agent.

Provides a simple interface to the agent's functionality.
Wires up the Brain, Body (ToolRegistry), and Router.
"""

import os
from typing import Dict, Any, Optional

from dotenv import load_dotenv

from core.brain import Brain
from core.registry import ToolRegistry
from core.router import Router
from llm.groq_adapter import GroqAdapter
from llm.mock_adapter import MockLLMAdapter


# Load environment variables
load_dotenv()


class LocalAgent:
    """
    High-level facade for the Windows Automation Agent.

    Wires up all components and provides a simple execute() interface.

    Args:
        use_smart_model: If True, uses 70B model for better reasoning (slower).
                         Default False uses 8B for speed.
    """

    def __init__(self, use_smart_model: bool = False):
        """
        Initialize the agent.

        Args:
            use_smart_model: Use 70B model instead of 8B
        """
        api_key = os.environ.get("GROQ_API_KEY")

        # Create LLM client
        if api_key:
            llm_client = GroqAdapter(api_key=api_key, use_smart_model=use_smart_model)
            model_name = "70B (Smart)" if use_smart_model else "8B (Fast)"
            print(f"[AGENT] Using Groq model: {model_name}")
        else:
            print("[WARNING] No GROQ_API_KEY found. Agent will run in MOCK mode.")
            llm_client = MockLLMAdapter()

        # Wire up components
        self.body = ToolRegistry()
        self.brain = Brain(llm_client)
        self.router = Router(self.brain, self.body)
        self.router.start_session()

        # Expose registry for compatibility
        self.tool_registry = self.body._registry

    def execute(self, user_input: str) -> Optional[Dict[str, Any]]:
        """
        Execute a user command.

        Atomic execution: Input -> Tool -> Result.
        No loops, no retries. Fail fast.

        Args:
            user_input: The user's command/request

        Returns:
            Result dict with 'status' and other tool-specific data
        """
        print(f"\nUser: '{user_input}'")

        result = self.router.process(user_input)

        status_icon = "[OK]" if result.get("status") == "success" else "[ERR]"
        print(f"{status_icon} Result: {result}")

        # Show HUD state
        if self.router.context:
            print(self.router.context.get_hud())

        return result

    @property
    def session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self.router.context.session_id if self.router.context else None

    @property
    def cwd(self) -> Optional[str]:
        """Get the current working directory."""
        return self.router.context.cwd if self.router.context else None
