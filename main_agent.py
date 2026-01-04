"""
Windows Automation Agent with Atomic Router Architecture.

This agent uses a Groq LLM to interpret natural language commands
and execute them using Windows system tools.

Architecture:
- AgentContext: State-focused context with HUD (last action, focused window, cwd)
- ToolRegistry (Body): Stateless tool executor
- Brain: LLM Router - maps intent to single tool
- Router: Atomic executor (no loops, no retries, fail fast)
- LocalAgent: Backward-compatible facade

Design Philosophy: "Stateful Context, Atomic Action"
- User acts as the Orchestrator
- Agent acts as the Bionic Arm
- Short-term memory (2 turns) for "it/that" resolution
"""

import os
import json
import time
import re
import uuid
import getpass
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Callable, Deque
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
    State-focused context for atomic execution.
    Tracks system state (HUD) rather than conversation history.

    Key design: "Stateful Context, Atomic Action"
    - Short-term memory (2 turns) for "it/that" resolution
    - State tracking (last action, focused window) for context-aware decisions
    """
    # --- Session State ---
    session_id: str

    # --- Short-term Memory (Only 2 turns for "it/that" resolution) ---
    short_term_history: Deque[ConversationTurn] = field(default_factory=lambda: deque(maxlen=2))

    # --- Environment State ---
    cwd: str = field(default_factory=lambda: os.path.expanduser("~"))
    user: str = field(default_factory=getpass.getuser)
    timestamp: datetime = field(default_factory=datetime.now)

    # --- State Tracking (The "HUD") ---
    last_tool_output: Optional[Dict[str, Any]] = None
    focused_window_cache: Optional[Dict[str, Any]] = None

    def add_turn(self, role: str, content: str, **kwargs):
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

    def update_state(self, tool_result: Dict[str, Any]):
        """
        Update state tracking after tool execution.
        Extracts target info for the HUD display.
        """
        self.last_tool_output = tool_result

        # If the tool returned a target with window info, cache it
        if "target" in tool_result:
            target = tool_result["target"]
            if "title" in target or "id" in target:
                self.focused_window_cache = target

    def refresh_environment(self, windows_manager=None):
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
        """Estimate tokens used by history. Rough estimate: 1 token ≈ 4 chars."""
        total_chars = sum(len(turn.content) for turn in self.short_term_history)
        return total_chars // 4

    def get_context_usage(self, system_prompt_tokens: int = 1500) -> tuple:
        """
        Returns (used_tokens, max_tokens, percentage).
        Groq Llama models have 8192 token context window.
        """
        max_tokens = 8192
        history_tokens = self.estimate_context_tokens()
        used = system_prompt_tokens + history_tokens
        pct = min(100, int((used / max_tokens) * 100))
        return used, max_tokens, pct


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
            "turn_screen_on": self.hardware.turn_screen_on,

            # --- Windows ---
            "list_windows": self.windows.list_open_windows,
            "focus_window": self.windows.focus_window,
            "minimize_window": self.windows.minimize_window,
            "minimize_all": self.windows.minimize_all,  # Safe batch minimize (keeps Explorer)
            "restore_all": self.windows.restore_all,  # Undo button - restore minimized
            "maximize_all": self.windows.maximize_all,  # Smart batch maximize
            "close_window": self.windows.close_window,
            "list_desktops": self.windows.list_desktops,
            "switch_desktop": self.windows.switch_desktop,
            "move_window": self.windows.move_window_to_desktop,

            # --- Text Input ---
            "type_text": self.windows.type_text,  # Type or paste text

            # --- System ---
            "list_files": self.system.list_directory,
            "get_sys_info": self.system.get_system_info,
            "check_processes": self.system.list_processes,
            "delete_item": self.system.delete_item,
            "get_env": self.system.get_environment_variable,
            "list_usb": self.system.list_usb_devices,
            "change_dir": self.system.change_directory,

            # --- App Launcher (with auto-focus) & Clipboard ---
            "launch_app": self.windows.launch_app,  # Uses poll-and-focus
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

    Two-Gear Strategy:
    - 8B (default): Fast (~1200 t/s), good for simple commands
    - 70B (fallback): Smarter (~300 t/s), for complex reasoning
    """
    MODEL_FAST = "llama-3.1-8b-instant"      # The Intern - fast but limited
    MODEL_SMART = "llama-3.1-70b-versatile"  # The Senior - slower but smarter

    def __init__(self, client, model: str = None, use_smart_model: bool = False):
        self.client = client
        self.model = model or (self.MODEL_SMART if use_smart_model else self.MODEL_FAST)

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
                temperature=0.0,
                max_tokens=512  # Keep output concise for context limits
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

        # Screen commands
        if "screen" in user_lower:
            if "off" in user_lower or "turn off" in user_lower:
                return {"tool": "turn_screen_off", "args": {}}
            if "on" in user_lower or "wake" in user_lower:
                return {"tool": "turn_screen_on", "args": {}}

        # Brightness commands
        if "brightness" in user_lower:
            nums = re.findall(r'\d+', user_input)
            level = int(nums[0]) if nums else 50
            return {"tool": "set_brightness", "args": {"level": level}}

        # USB devices
        if "usb" in user_lower and ("list" in user_lower or "show" in user_lower or "device" in user_lower):
            return {"tool": "list_usb", "args": {}}

        # Environment variables
        if "env" in user_lower or "path" in user_lower.split():
            if "path" in user_lower:
                return {"tool": "get_env", "args": {"var_name": "PATH"}}
            match = re.search(r"['\"]([^'\"]+)['\"]", user_input)
            if match:
                return {"tool": "get_env", "args": {"var_name": match.group(1)}}
            return {"tool": "get_env", "args": {"var_name": "PATH"}}

        # Change directory
        if "cd " in user_lower or "change dir" in user_lower or "navigate to" in user_lower:
            if "download" in user_lower:
                return {"tool": "change_dir", "args": {"path": "~/Downloads"}}
            if "desktop" in user_lower:
                return {"tool": "change_dir", "args": {"path": "~/Desktop"}}
            if "home" in user_lower:
                return {"tool": "change_dir", "args": {"path": "~"}}
            # Try to extract path
            match = re.search(r"['\"]([^'\"]+)['\"]", user_input)
            if match:
                return {"tool": "change_dir", "args": {"path": match.group(1)}}
            return {"tool": "change_dir", "args": {"path": "~"}}

        # Multi-step commands: "Open X and type Y" - ATOMIC: pick first action only
        if ("open" in user_lower or "launch" in user_lower) and ("type" in user_lower or "paste" in user_lower):
            app = "notepad"  # Default
            for a in ["notepad", "chrome", "code"]:
                if a in user_lower:
                    app = a
                    break
            # Atomic: only launch the app, user will issue type command next
            return {"tool": "launch_app", "args": {"app_name": app}}

        # Launch app commands (single action)
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
                # Try to extract text in quotes
                match = re.search(r"['\"]([^'\"]+)['\"]", user_input)
                if match:
                    return {"tool": "set_clipboard", "args": {"text": match.group(1)}}

        # "Copy X to clipboard" (without the word clipboard first)
        if "copy" in user_lower and "clipboard" in user_lower:
            match = re.search(r"['\"]([^'\"]+)['\"]", user_input)
            if match:
                return {"tool": "set_clipboard", "args": {"text": match.group(1)}}

        # Batch minimize: "minimize all X windows" or "minimize all"
        if "minimize" in user_lower and "all" in user_lower:
            for app in ["chrome", "firefox", "notepad", "code", "explorer"]:
                if app in user_lower:
                    return {"tool": "minimize_all", "args": {"filter_name": app}}
            return {"tool": "minimize_all", "args": {}}

        # Single window minimize
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
# ROUTER (ATOMIC EXECUTOR)
# =============================================================================

class Router:
    """
    Atomic Executor - maps Intent -> Tool -> Result.
    No loops. No retries. Fail fast.

    Design philosophy: "Stateful Context, Atomic Action"
    - User acts as the "Orchestrator"
    - Agent acts as the "Bionic Arm"
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

    # Tools that need latency injection (wait for UI to appear)
    LATENCY_TOOLS = {
        "open_explorer": 1.0,   # Wait 1s for Explorer window
        "focus_window": 0.3,    # Brief wait for focus change
    }

    def process(self, user_input: str) -> Dict[str, Any]:
        """
        Atomic Execution: Input -> LLM -> Tool -> Result.
        No loops. No retries. Fail fast.
        """
        if not self.context:
            self.start_session()

        # 1. Refresh Context (Only what's needed for THIS decision)
        self.context.refresh_environment(self.body.windows)
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
            if tool_name in self.LATENCY_TOOLS and result.get("status") == "success":
                delay = self.LATENCY_TOOLS[tool_name]
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


# =============================================================================
# LOCAL AGENT (BACKWARD-COMPATIBLE FACADE)
# =============================================================================

class LocalAgent:
    """
    Backward-compatible facade that wraps the Router architecture.
    Provides the same interface as the original LocalAgent.

    Args:
        use_smart_model: If True, uses 70B model for better reasoning (slower).
                         Default False uses 8B for speed.
    """

    def __init__(self, use_smart_model: bool = False):
        api_key = os.environ.get("GROQ_API_KEY")

        if api_key:
            client = Groq(api_key=api_key)
        else:
            print("[WARNING] No GROQ_API_KEY found. Agent will run in MOCK mode.")
            client = None

        self.body = ToolRegistry()
        self.brain = Brain(client, use_smart_model=use_smart_model)
        self.router = Router(self.brain, self.body)
        self.router.start_session()

        # Expose for backward compatibility
        self.tool_registry = self.body._registry

        model_name = "70B (Smart)" if use_smart_model else "8B (Fast)"
        print(f"[AGENT] Using model: {model_name}")

    def execute(self, user_input: str) -> Optional[Dict[str, Any]]:
        """
        Atomic execution: Input -> Tool -> Result.
        No loops, no retries. Fail fast.
        """
        print(f"\nUser: '{user_input}'")

        result = self.router.process(user_input)

        status_icon = "[OK]" if result.get("status") == "success" else "[ERR]"
        print(f"{status_icon} Result: {result}")

        # Show HUD state
        if self.router.context:
            print(self.router.context.get_hud())

        return result


# =============================================================================
# TEST COMMANDS
# =============================================================================

TEST_COMMANDS = [
    # Basic commands
    "Set brightness to 50",
    "List all open windows",
    "Focus Chrome",
    "Show system info",
    # App launching
    "Open Notepad",
    "Open Downloads folder",
    "Launch Calculator",
    # New tools
    "Wake up the screen",
    "Show USB devices",
    "Show PATH variable",
    "Change directory to Downloads",
    # Batch operations (smart tools)
    "Minimize all Chrome windows",
    "Minimize all windows",
    # Clipboard
    "Get clipboard content",
    "Copy 'test message' to clipboard",
    # Type (after opening app)
    "Type 'Hello World'",
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
    import sys

    # Setup readline for arrow key history navigation
    try:
        import readline
    except ImportError:
        try:
            import pyreadline3 as readline
        except ImportError:
            readline = None

    # Pre-populate history with test commands (reverse so first is most recent)
    if readline:
        for cmd in reversed(TEST_COMMANDS):
            readline.add_history(cmd)

    # Check for --smart flag to use 70B model
    use_smart = "--smart" in sys.argv or "-s" in sys.argv

    agent = LocalAgent(use_smart_model=use_smart)

    print("[AGENT] Windows Automation Agent Initialized (Atomic Mode).")
    print(f"[AGENT] Session: {agent.router.context.session_id}")
    print(f"[AGENT] Working Directory: {agent.router.context.cwd}")
    print("Tip: Use UP/DOWN arrows to cycle through commands. '--smart' for 70B model.")
    show_menu()  # Show menu once at start

    while True:
        req = input("\n> ").strip()

        if req.lower() in ["exit", "quit", "q"]:
            print("Goodbye!")
            break

        if req.lower() == "help":
            show_menu()
            continue

        if not req:
            continue

        agent.execute(req)
