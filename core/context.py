"""
Context management for the Windows Automation Agent.

Contains:
- ConversationTurn: Single turn in the conversation history
- AgentContext: State-focused context with HUD for atomic execution
"""

import os
import getpass
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Deque

from core.constants import SHORT_TERM_MEMORY_SIZE, MAX_CONTEXT_TOKENS


@dataclass
class ConversationTurn:
    """Single turn in the conversation history."""
    role: str  # "user" | "assistant" | "tool_result"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None


@dataclass
class AgentContext:
    """
    State-focused context for atomic execution.
    Tracks system state (HUD) rather than conversation history.

    Key design: "Stateful Context, Atomic Action"
    - Short-term memory (2 turns) for "it/that" resolution
    - State tracking (last action, focused window) for context-aware decisions
    """

    # --- Session State ---
    session_id: str

    # --- Short-term Memory (Only 2 turns for "it/that" resolution) ---
    short_term_history: Deque[ConversationTurn] = field(
        default_factory=lambda: deque(maxlen=SHORT_TERM_MEMORY_SIZE)
    )

    # --- Environment State ---
    cwd: str = field(default_factory=lambda: os.path.expanduser("~"))
    user: str = field(default_factory=getpass.getuser)
    timestamp: datetime = field(default_factory=datetime.now)

    # --- State Tracking (The "HUD") ---
    last_tool_output: Optional[Dict[str, Any]] = None
    focused_window_cache: Optional[Dict[str, Any]] = None

    def add_turn(self, role: str, content: str, **kwargs) -> None:
        """Add a conversation turn. Deque auto-removes oldest entries (keeps last 2)."""
        if len(content) > 1000:
            content = content[:1000] + "... [TRUNCATED]"
        turn = ConversationTurn(role=role, content=content, **kwargs)
        self.short_term_history.append(turn)

    def get_history_for_prompt(self) -> List[Dict[str, str]]:
        """Format short-term history for LLM messages array."""
        messages = []
        for turn in self.short_term_history:
            if turn.role == "tool_result":
                messages.append({
                    "role": "assistant",
                    "content": f"[Tool: {turn.tool_name}] Result: {turn.content}"
                })
            else:
                messages.append({"role": turn.role, "content": turn.content})
        return messages

    def update_state(self, tool_result: Dict[str, Any]) -> None:
        """
        Update state tracking after tool execution.
        Extracts target info for the HUD display.
        """
        self.last_tool_output = tool_result

        # If the tool returned a target with window info, cache it
        if "target" in tool_result:
            target = tool_result["target"]
            if isinstance(target, dict) and ("title" in target or "id" in target):
                self.focused_window_cache = target

    def refresh_environment(self, windows_manager=None) -> None:
        """Refresh dynamic environment state."""
        self.timestamp = datetime.now()
        # Update cwd in case change_dir was used
        self.cwd = os.getcwd()

        if windows_manager:
            try:
                result = windows_manager.list_open_windows()
                windows = result.get("windows", [])
                if windows:
                    # Parse first window: "1. Notepad" -> {"id": 1, "title": "Notepad"}
                    first = windows[0]
                    parts = first.split(". ", 1)
                    if len(parts) == 2:
                        self.focused_window_cache = {
                            "id": int(parts[0]),
                            "title": parts[1]
                        }
            except Exception:
                pass

    def get_hud(self) -> str:
        """
        Generate the Heads-Up Display for the system prompt.
        Shows current system state for context-aware decisions.
        """
        # Format last action
        last_action_str = "None"
        if self.last_tool_output:
            action = self.last_tool_output.get("action", "unknown")
            target = self.last_tool_output.get("target", {})
            if isinstance(target, dict):
                target_name = target.get("title", target.get("path", target.get("app_name", "")))
            else:
                target_name = str(target)
            if target_name:
                last_action_str = f"{action} -> {target_name}"
            else:
                last_action_str = action

        # Format focused window
        focused_str = "Unknown"
        if self.focused_window_cache:
            title = self.focused_window_cache.get("title", "Unknown")
            win_id = self.focused_window_cache.get("id", "?")
            focused_str = f"{title} (ID: {win_id})"

        return f"""[SYSTEM STATUS]
- Active Focus: {focused_str}
- Last Action: {last_action_str}
- Working Dir: {self.cwd}
- Time: {self.timestamp.strftime('%H:%M:%S')}"""

    def estimate_context_tokens(self) -> int:
        """Estimate tokens used by history. Rough estimate: 1 token ~ 4 chars."""
        total_chars = sum(len(turn.content) for turn in self.short_term_history)
        return total_chars // 4

    def get_context_usage(self, system_prompt_tokens: int = 1500) -> tuple:
        """
        Returns (used_tokens, max_tokens, percentage).
        Groq Llama models have 8192 token context window.
        """
        history_tokens = self.estimate_context_tokens()
        used = system_prompt_tokens + history_tokens
        pct = min(100, int((used / MAX_CONTEXT_TOKENS) * 100))
        return used, MAX_CONTEXT_TOKENS, pct
