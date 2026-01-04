"""
Protocol definitions for the Windows Automation Agent.

These protocols define the contracts between components, enabling:
- Dependency injection
- Easy mocking for tests
- Swappable implementations (e.g., different LLM providers)

Following Dependency Inversion Principle (DIP): depend on abstractions, not concretions.
"""

from typing import Protocol, Dict, Any, Optional, Callable, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import AgentContext


class LLMClient(Protocol):
    """
    Abstraction for any LLM provider (Groq, OpenAI, Anthropic, Mock).

    Implementations must provide a `complete` method that takes messages
    and returns a string response.
    """

    def complete(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Send messages to the LLM and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            **kwargs: Provider-specific options (temperature, max_tokens, etc.)

        Returns:
            The LLM's response as a string
        """
        ...


class DecisionMaker(Protocol):
    """
    The Brain interface - maps user intent to tool selection.

    Takes context and user input, returns a decision dict with
    'tool' and 'args' keys.
    """

    def decide(self, context: "AgentContext", user_input: str) -> Dict[str, Any]:
        """
        Make a single atomic decision based on context and input.

        Args:
            context: Current agent context with HUD state
            user_input: The user's command/request

        Returns:
            Decision dict: {"tool": "tool_name", "args": {...}}
            Or error: {"tool": "error", "args": {"message": "reason"}}
        """
        ...


class ToolExecutor(Protocol):
    """
    The Body interface - executes tools by name.

    Provides access to registered tools and their execution.
    """

    def get(self, tool_name: str) -> Optional[Callable]:
        """
        Get a tool function by name.

        Args:
            tool_name: The registered name of the tool

        Returns:
            The callable tool function, or None if not found
        """
        ...

    def list_tools(self) -> List[str]:
        """
        List all available tool names.

        Returns:
            List of registered tool names
        """
        ...


class StateManager(Protocol):
    """
    The Router/Orchestrator interface - manages execution flow.

    Coordinates between Brain (decision) and Body (execution).
    """

    def process(self, user_input: str) -> Dict[str, Any]:
        """
        Process a user input through the full pipeline.

        Args:
            user_input: The user's command/request

        Returns:
            Result dict with 'status' and other tool-specific data
        """
        ...

    def start_session(self) -> str:
        """
        Initialize a new session.

        Returns:
            The new session ID
        """
        ...

    def end_session(self) -> None:
        """Clean up session state."""
        ...


class SafetyGate(Protocol):
    """
    Handles confirmation for destructive actions.
    """

    def requires_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires user confirmation."""
        ...

    def confirm(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """
        Prompt user for confirmation.

        Returns:
            True if user confirms, False otherwise
        """
        ...


class OutputSanitizer(Protocol):
    """
    Truncates/sanitizes large outputs to prevent context flooding.
    """

    def sanitize(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize a tool result (e.g., truncate large lists).

        Args:
            result: Raw tool result

        Returns:
            Sanitized result
        """
        ...
