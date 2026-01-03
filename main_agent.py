"""
Windows Automation Agent with Brain/Body/Orchestrator Architecture.

This agent uses a Groq LLM to interpret natural language commands
and execute them using Windows system tools.

Architecture:
- AgentContext: Holds session state (history, cwd, user info)
- ToolRegistry (Body): Stateless tool executor
- Brain: LLM decision maker
- Orchestrator: Coordinates Brain and Body, manages state
- LocalAgent: Backward-compatible facade
"""

import os
import json
import time
import re
import uuid
import getpass
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Callable
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import our custom toolkits
from tools.hardware_tools import HardwareController
from tools.windows_tools import WindowManager
from tools.system_tools import SystemTools

# Import LLM Client (Using Groq for speed)
from groq import Groq


# =============================================================================
# DATA CLASSES
# =============================================================================

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
    Stateful context passed to Brain for every decision.
    Contains all environmental information the LLM needs.
    """
    # --- Session State ---
    session_id: str
    history: List[ConversationTurn] = field(default_factory=list)
    max_history: int = 10  # Last N turns to include in prompt

    # --- Environment State ---
    cwd: str = field(default_factory=lambda: os.path.expanduser("~"))
    user: str = field(default_factory=getpass.getuser)
    timestamp: datetime = field(default_factory=datetime.now)

    # --- Window State (refreshed per turn) ---
    active_window: Optional[str] = None

    # --- Execution Tracking ---
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None

    def add_turn(self, role: str, content: str, **kwargs):
        """Add a conversation turn and trim history if needed."""
        turn = ConversationTurn(role=role, content=content, **kwargs)
        self.history.append(turn)
        # Trim to max_history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_history_for_prompt(self) -> List[Dict[str, str]]:
        """Format history for LLM messages array."""
        messages = []
        for turn in self.history:
            if turn.role == "tool_result":
                # Format tool results as assistant messages
                messages.append({
                    "role": "assistant",
                    "content": f"[Tool: {turn.tool_name}] Result: {turn.content}"
                })
            else:
                messages.append({"role": turn.role, "content": turn.content})
        return messages

    def refresh_environment(self, windows_manager=None):
        """Refresh dynamic environment state."""
        self.timestamp = datetime.now()
        if windows_manager:
            try:
                result = windows_manager.list_open_windows()
                windows = result.get("windows", [])
                self.active_window = windows[0] if windows else None
            except Exception:
                self.active_window = None


# =============================================================================
# CONSTANTS
# =============================================================================

# Destructive actions that require user confirmation
DESTRUCTIVE_ACTIONS = {
    "delete_item": {
        "risk": "HIGH",
        "message": "DELETE file/folder",
        "target_key": "path"
    },
    "close_window": {
        "risk": "MEDIUM",
        "message": "CLOSE application window",
        "target_key": "app_name"
    },
}


# =============================================================================
# TOOL REGISTRY (THE "BODY")
# =============================================================================

class ToolRegistry:
    """
    Stateless tool executor - the 'Body'.
    Maps tool names to functions and executes them.
    """

    def __init__(self):
        self.hardware = HardwareController()
        self.windows = WindowManager()
        self.system = SystemTools()

        self._registry: Dict[str, Callable] = {
            # --- Hardware ---
            "set_brightness": self.hardware.set_brightness,
            "turn_screen_off": self.hardware.turn_screen_off,

            # --- Windows ---
            "list_windows": self.windows.list_open_windows,
            "focus_window": self.windows.focus_window,
            "minimize_window": self.windows.minimize_window,
            "close_window": self.windows.close_window,
            "list_desktops": self.windows.list_desktops,
            "switch_desktop": self.windows.switch_desktop,
            "move_window": self.windows.move_window_to_desktop,

            # --- System ---
            "list_files": self.system.list_directory,
            "get_sys_info": self.system.get_system_info,
            "check_processes": self.system.list_processes,
            "delete_item": self.system.delete_item,

            # --- New Tools ---
            "launch_app": self.system.launch_app,
            "open_explorer": self.system.open_explorer,
            "get_clipboard": self.system.get_clipboard,
            "set_clipboard": self.system.set_clipboard,
        }

    def get(self, tool_name: str) -> Optional[Callable]:
        """Get a tool function by name."""
        return self._registry.get(tool_name)

    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return list(self._registry.keys())


# =============================================================================
# BRAIN (THE DECISION MAKER)
# =============================================================================

class Brain:
    """
    Atomic Decision Maker - stateless LLM wrapper.
    Takes context + query, outputs JSON decision.
    """

    def __init__(self, client, model: str = "llama-3.1-8b-instant"):
        self.client = client
        self.model = model

    def _build_system_prompt(self, context: AgentContext) -> str:
        """Build system prompt with context awareness."""
        tools_spec = """
Tools and their EXACT argument names:
- set_brightness: args: {"level": <int 0-100>}
- turn_screen_off: args: {}
- list_windows: args: {}
- focus_window: args: {"app_name": "<window name>"}
- minimize_window: args: {"app_name": "<window name>"}
- close_window: args: {"app_name": "<window name>"} [DESTRUCTIVE - requires confirmation]
- list_desktops: args: {} - returns current desktop index and total count
- switch_desktop: args: {"index": <int>} - desktop indexes start at 1
- move_window: args: {"app_name": "<window name>", "desktop_index": <int>}
- list_files: args: {"path": "<directory path>"}
- get_sys_info: args: {}
- check_processes: args: {"filter_name": "<optional process name>"} or {}
- delete_item: args: {"path": "<file/folder path>", "confirm": true} [DESTRUCTIVE - requires confirmation]
- launch_app: args: {"app_name": "<app name like 'notepad', 'chrome', 'calc'>"}
- open_explorer: args: {"path": "<folder path>"}
- get_clipboard: args: {}
- set_clipboard: args: {"text": "<text to copy>"}

IMPORTANT:
- When user says "current desktop", first call list_desktops to get the current_index.
- All argument values must be the correct type: integers for index/level, strings for names/paths.
- For paths, you can use ~ to refer to the user's home directory.
"""

        context_info = f"""
Current Context:
- Working Directory: {context.cwd}
- User: {context.user}
- Time: {context.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- Active Window: {context.active_window or 'Unknown'}
"""

        error_context = ""
        if context.last_error and context.retry_count > 0:
            error_context = f"""
Previous Error (Retry {context.retry_count}/{context.max_retries}):
{context.last_error}
Please try a different approach or correct the error.
"""

        return (
            "You are a Windows Automation Agent.\n"
            f"{tools_spec}\n"
            f"{context_info}\n"
            f"{error_context}"
            "Output ONLY a single JSON object (not an array): {\"tool\": \"tool_name\", \"args\": {\"arg_name\": \"value\"}}\n"
            "Execute ONE action at a time. For multi-step tasks, do the first step only.\n"
            "If impossible, output: {\"tool\": \"error\", \"args\": {\"message\": \"reason\"}}"
        )

    def decide(self, context: AgentContext, user_input: str) -> Dict[str, Any]:
        """
        Make a single atomic decision based on context and input.
        """
        if not self.client:
            return self._mock_decide(user_input)

        try:
            # Build messages with history
            messages = [
                {"role": "system", "content": self._build_system_prompt(context)}
            ]
            messages.extend(context.get_history_for_prompt())

            # Add current request if not already the last message
            if not context.history or context.history[-1].content != user_input:
                messages.append({"role": "user", "content": user_input})

            start = time.time()
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0
            )
            latency = (time.time() - start) * 1000

            response_text = completion.choices[0].message.content
            print(f"[LLM] Decision ({latency:.0f}ms): {response_text}")
            return json.loads(response_text)

        except Exception as e:
            return {"tool": "error", "args": {"message": f"LLM failure: {e}"}}

    def _mock_decide(self, user_input: str) -> Dict[str, Any]:
        """Mock decision logic for testing without API key."""
        user_lower = user_input.lower()

        # Brightness commands
        if "brightness" in user_lower:
            nums = re.findall(r'\d+', user_input)
            level = int(nums[0]) if nums else 50
            return {"tool": "set_brightness", "args": {"level": level}}

        # Launch app commands
        if "open" in user_lower or "launch" in user_lower or "start" in user_lower:
            for app in ["notepad", "chrome", "firefox", "code", "calculator", "calc", "edge"]:
                if app in user_lower:
                    return {"tool": "launch_app", "args": {"app_name": app}}

            # Check for explorer/folder
            if "explorer" in user_lower or "folder" in user_lower:
                if "download" in user_lower:
                    return {"tool": "open_explorer", "args": {"path": "~/Downloads"}}
                if "desktop" in user_lower:
                    return {"tool": "open_explorer", "args": {"path": "~/Desktop"}}
                return {"tool": "open_explorer", "args": {"path": "."}}

        # Clipboard commands
        if "clipboard" in user_lower:
            if "get" in user_lower or "read" in user_lower or "show" in user_lower:
                return {"tool": "get_clipboard", "args": {}}
            if "copy" in user_lower or "set" in user_lower:
                # Try to extract text after "copy" or in quotes
                match = re.search(r'"([^"]+)"', user_input)
                if match:
                    return {"tool": "set_clipboard", "args": {"text": match.group(1)}}

        # Window commands
        if "minimize" in user_lower:
            for app in ["notepad", "chrome", "firefox", "code", "explorer"]:
                if app in user_lower:
                    return {"tool": "minimize_window", "args": {"app_name": app.title()}}
            return {"tool": "minimize_window", "args": {"app_name": "Notepad"}}

        if "focus" in user_lower:
            for app in ["notepad", "chrome", "firefox", "code", "explorer"]:
                if app in user_lower:
                    return {"tool": "focus_window", "args": {"app_name": app.title()}}
            return {"tool": "focus_window", "args": {"app_name": "Chrome"}}

        if "close" in user_lower and "window" in user_lower:
            for app in ["notepad", "chrome", "firefox", "code"]:
                if app in user_lower:
                    return {"tool": "close_window", "args": {"app_name": app.title()}}

        if "list" in user_lower and "window" in user_lower:
            return {"tool": "list_windows", "args": {}}

        # File commands
        if "list" in user_lower and "file" in user_lower:
            if "download" in user_lower:
                return {"tool": "list_files", "args": {"path": "~/Downloads"}}
            if "desktop" in user_lower:
                return {"tool": "list_files", "args": {"path": "~/Desktop"}}
            return {"tool": "list_files", "args": {"path": "."}}

        # System commands
        if "system" in user_lower or "sys info" in user_lower:
            return {"tool": "get_sys_info", "args": {}}

        if "process" in user_lower:
            if "python" in user_lower:
                return {"tool": "check_processes", "args": {"filter_name": "python"}}
            if "chrome" in user_lower:
                return {"tool": "check_processes", "args": {"filter_name": "chrome"}}
            return {"tool": "check_processes", "args": {}}

        # Desktop commands
        if "desktop" in user_lower and "switch" in user_lower:
            nums = re.findall(r'\d+', user_input)
            idx = int(nums[0]) if nums else 1
            return {"tool": "switch_desktop", "args": {"index": idx}}

        return {"tool": "error", "args": {"message": "Mock mode: Unknown command"}}


# =============================================================================
# ORCHESTRATOR (THE STATE MANAGER)
# =============================================================================

class Orchestrator:
    """
    The State Manager - coordinates Brain (decisions) and Body (tools).
    Handles:
    - Session lifecycle
    - Conversation history
    - Error recovery loop
    - Destructive action interception
    """

    def __init__(self, brain: Brain, body: ToolRegistry):
        self.brain = brain
        self.body = body
        self.context: Optional[AgentContext] = None

    def start_session(self) -> str:
        """Initialize a new session with fresh context."""
        session_id = str(uuid.uuid4())[:8]
        self.context = AgentContext(session_id=session_id)
        return session_id

    def end_session(self):
        """Clean up session state."""
        self.context = None

    def _confirm_destructive_action(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """
        Intercept destructive actions and prompt user for confirmation.
        Returns True if user confirms, False otherwise.
        """
        if tool_name not in DESTRUCTIVE_ACTIONS:
            return True  # Non-destructive, proceed

        config = DESTRUCTIVE_ACTIONS[tool_name]
        target = args.get(config["target_key"], str(args))

        print(f"\n{'='*50}")
        print(f"[SAFETY - {config['risk']} RISK] Destructive action requested:")
        print(f"  Action: {config['message']}")
        print(f"  Target: {target}")
        print(f"{'='*50}")

        response = input("Type 'yes' to confirm: ").strip().lower()
        return response == "yes"

    def _sanitize_output(self, result: Dict[str, Any], max_items: int = 50) -> Dict[str, Any]:
        """Truncate large results to prevent context flooding."""
        if "items" in result and isinstance(result["items"], list):
            items = result["items"]
            if len(items) > max_items:
                result["items"] = items[:max_items]
                result["truncated"] = True
                result["total_count"] = len(items)

        if "processes" in result and isinstance(result["processes"], list):
            procs = result["processes"]
            if len(procs) > max_items:
                result["processes"] = procs[:max_items]
                result["truncated"] = True
                result["total_count"] = len(procs)

        if "windows" in result and isinstance(result["windows"], list):
            windows = result["windows"]
            if len(windows) > max_items:
                result["windows"] = windows[:max_items]
                result["truncated"] = True
                result["total_count"] = len(windows)

        return result

    def process(self, user_input: str) -> Dict[str, Any]:
        """
        Main execution pipeline with error recovery loop.
        Input -> Decide -> [Confirm] -> Act -> Feedback -> [Retry if error]
        """
        if not self.context:
            self.start_session()

        # Record user input
        self.context.add_turn("user", user_input)
        self.context.refresh_environment(self.body.windows)
        self.context.retry_count = 0
        self.context.last_error = None

        while self.context.retry_count <= self.context.max_retries:
            # 1. DECIDE (Brain)
            decision = self.brain.decide(self.context, user_input)

            # Handle LLM returning a list of actions
            if isinstance(decision, list):
                decision = decision[0] if decision else {"tool": "error", "args": {"message": "Empty action list"}}

            tool_name = decision.get("tool")
            args = decision.get("args", {})

            # Handle error/unknown from Brain
            if tool_name == "error":
                error_msg = args.get("message", "Unknown error")
                self.context.add_turn("assistant", f"Error: {error_msg}")
                return {"status": "error", "message": error_msg}

            # 2. CONFIRM (if destructive)
            if not self._confirm_destructive_action(tool_name, args):
                self.context.add_turn("assistant", f"Action cancelled by user: {tool_name}")
                return {"status": "cancelled", "message": f"User cancelled {tool_name}"}

            # 3. ACT (Body)
            func = self.body.get(tool_name)

            if not func:
                error_msg = f"Tool '{tool_name}' not found"
                self.context.add_turn("assistant", f"Error: {error_msg}")
                return {"status": "error", "message": error_msg}

            try:
                result = func(**args)
                result = self._sanitize_output(result)

                # 4. CHECK SUCCESS
                if result.get("status") == "success":
                    # Record success and return
                    self.context.add_turn(
                        "tool_result",
                        str(result),
                        tool_name=tool_name,
                        tool_args=args,
                        tool_result=result
                    )
                    return result

                # Tool returned error status - attempt recovery
                self.context.last_error = result.get("message", "Tool returned error")
                self.context.retry_count += 1

                if self.context.retry_count <= self.context.max_retries:
                    # Feed error back to Brain for retry
                    error_context = f"Previous attempt failed: {self.context.last_error}"
                    self.context.add_turn("tool_result", error_context, tool_name=tool_name)
                    print(f"[RETRY {self.context.retry_count}/{self.context.max_retries}] {error_context}")
                    continue
                else:
                    return result

            except TypeError as e:
                error_msg = f"Argument mismatch for {tool_name}: {e}"
                self.context.last_error = error_msg
                self.context.retry_count += 1

                if self.context.retry_count <= self.context.max_retries:
                    self.context.add_turn("tool_result", error_msg, tool_name=tool_name)
                    print(f"[RETRY {self.context.retry_count}/{self.context.max_retries}] {error_msg}")
                    continue
                else:
                    return {"status": "error", "message": error_msg}

            except Exception as e:
                error_msg = f"Execution failed: {e}"
                self.context.last_error = error_msg
                self.context.add_turn("assistant", f"Error: {error_msg}")
                return {"status": "error", "message": error_msg}

        # Max retries exceeded
        return {
            "status": "error",
            "message": f"Failed after {self.context.max_retries} retries: {self.context.last_error}"
        }


# =============================================================================
# LOCAL AGENT (BACKWARD-COMPATIBLE FACADE)
# =============================================================================

class LocalAgent:
    """
    Backward-compatible facade that wraps the new architecture.
    Provides the same interface as the original LocalAgent.
    """

    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")

        if api_key:
            client = Groq(api_key=api_key)
        else:
            print("[WARNING] No GROQ_API_KEY found. Agent will run in MOCK mode.")
            client = None

        self.body = ToolRegistry()
        self.brain = Brain(client)
        self.orchestrator = Orchestrator(self.brain, self.body)
        self.orchestrator.start_session()

        # Expose for backward compatibility
        self.tool_registry = self.body._registry

    def execute(self, user_input: str) -> Optional[Dict[str, Any]]:
        """
        Main execution method - same signature as before.
        """
        print(f"\nUser: '{user_input}'")

        result = self.orchestrator.process(user_input)

        status_icon = "[OK]" if result.get("status") == "success" else "[WARN]"
        print(f"{status_icon} Result: {result}")

        return result


# =============================================================================
# TEST COMMANDS
# =============================================================================

TEST_COMMANDS = [
    "Set brightness to 50",
    "Set brightness to 100",
    "List all open windows",
    "Minimize Notepad",
    "Focus Chrome",
    "List files in Downloads",
    "List files in Desktop",
    "Show system info",
    "Check running processes",
    "Find python processes",
    "Switch to desktop 2",
    # New commands
    "Open Notepad",
    "Open Downloads folder",
    "Get clipboard content",
    "Launch Calculator",
]


def show_menu():
    """Display the test commands menu."""
    print("\n" + "="*50)
    print("TEST COMMANDS (enter number or type your own):")
    print("="*50)
    for i, cmd in enumerate(TEST_COMMANDS, 1):
        print(f"  {i:2}. {cmd}")
    print("="*50)
    print("  0. Exit")
    print("="*50)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    agent = LocalAgent()

    print("[AGENT] Windows Automation Agent Initialized.")
    print(f"[AGENT] Session: {agent.orchestrator.context.session_id}")
    print(f"[AGENT] Working Directory: {agent.orchestrator.context.cwd}")
    print("Type a number to run a test command, or type your own command.")

    while True:
        show_menu()
        req = input("\n> ").strip()

        if req.lower() in ["exit", "quit", "0"]:
            print("Goodbye!")
            break

        # Check if input is a number (menu selection)
        if req.isdigit():
            idx = int(req)
            if 1 <= idx <= len(TEST_COMMANDS):
                req = TEST_COMMANDS[idx - 1]
                print(f"\n[SELECTED] {req}")
            else:
                print(f"[ERROR] Invalid selection. Choose 1-{len(TEST_COMMANDS)} or 0 to exit.")
                continue

        agent.execute(req)
