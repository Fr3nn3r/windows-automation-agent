import os
import json
import time
import re
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import our custom toolkits
from tools.hardware_tools import HardwareController
from tools.windows_tools import WindowManager
from tools.system_tools import SystemTools

# Import LLM Client (Using Groq for speed as requested)
# pip install groq
from groq import Groq

class LocalAgent:
    def __init__(self):
        # 1. Initialize Toolkits
        self.hardware = HardwareController()
        self.windows = WindowManager()
        self.system = SystemTools()
        
        # 2. Build the Tool Registry
        # This maps "string_names" -> (function_reference, description)
        self.tool_registry = {
            # --- Hardware ---
            "set_brightness": self.hardware.set_brightness,
            "turn_screen_off": self.hardware.turn_screen_off,
            
            # --- Windows ---
            "list_windows": self.windows.list_open_windows,
            "focus_window": self.windows.focus_window,
            "minimize_window": self.windows.minimize_window,
            "list_desktops": self.windows.list_desktops,
            "switch_desktop": self.windows.switch_desktop,
            "move_window": self.windows.move_window_to_desktop,
            
            # --- System ---
            "list_files": self.system.list_directory,
            "get_sys_info": self.system.get_system_info,
            "check_processes": self.system.list_processes,
            "delete_item": self.system.delete_item, # Protected by confirm=True
        }
        
        # 3. Setup LLM Client
        self.api_key = os.environ.get("GROQ_API_KEY")
        if self.api_key:
            self.client = Groq(api_key=self.api_key)
        else:
            print("[WARNING] No GROQ_API_KEY found. Agent will run in MOCK mode.")
            self.client = None

    def _get_system_prompt(self) -> str:
        """
        Dynamically builds the system prompt based on available tools.
        This ensures the LLM knows exactly what it can do.
        """
        tools_with_args = """
Tools and their EXACT argument names:
- set_brightness: args: {"level": <int 0-100>}
- turn_screen_off: args: {}
- list_windows: args: {}
- focus_window: args: {"app_name": "<window name>"}
- minimize_window: args: {"app_name": "<window name>"}
- list_desktops: args: {} - returns current desktop index and total count
- switch_desktop: args: {"index": <int>} - desktop indexes start at 1
- move_window: args: {"app_name": "<window name>", "desktop_index": <int>} - desktop indexes start at 1
- list_files: args: {"path": "<directory path>"}
- get_sys_info: args: {}
- check_processes: args: {"filter_name": "<optional process name>"} or {}
- delete_item: args: {"path": "<file/folder path>", "confirm": true}

IMPORTANT: When user says "current desktop", first call list_desktops to get the current_index, then use that value.
All argument values must be the correct type: integers for index/level, strings for names/paths.
"""
        return (
            "You are a Windows Automation Agent.\n"
            f"{tools_with_args}\n"
            "You must output ONLY valid JSON in this format:\n"
            '{"tool": "tool_name", "args": {"arg_name": "value"}}\n'
            "Use the EXACT argument names shown above. For example, use 'app_name' not 'title'.\n"
            "If the user asks for something impossible, output: {\"tool\": \"error\", \"args\": {\"message\": \"reason\"}}"
        )

    def _call_llm(self, user_input: str) -> Dict[str, Any]:
        """
        Sends the user request to Groq and parses the JSON response.
        """
        if not self.client:
            # Mock Logic for testing without API key
            user_lower = user_input.lower()

            # Brightness commands
            if "brightness" in user_lower:
                # Try to extract number from input
                nums = re.findall(r'\d+', user_input)
                level = int(nums[0]) if nums else 50
                return {"tool": "set_brightness", "args": {"level": level}}

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

        try:
            start = time.time()
            completion = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": user_input}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            latency = (time.time() - start) * 1000
            response_text = completion.choices[0].message.content
            print(f"[LLM] Reasoning ({latency:.0f}ms): {response_text}")
            return json.loads(response_text)
            
        except Exception as e:
            return {"tool": "error", "args": {"message": f"LLM Failure: {str(e)}"}}

    def execute(self, user_input: str):
        """
        Main execution pipeline: Input -> Decide -> Act -> Feedback
        """
        print(f"\nUser: '{user_input}'")
        
        # 1. DECIDE (LLM)
        decision = self._call_llm(user_input)
        
        tool_name = decision.get("tool")
        args = decision.get("args", {})
        
        # 2. ACT (Dispatcher)
        if tool_name == "error":
            print(f"[ERROR] Agent Error: {args.get('message')}")
            return

        func = self.tool_registry.get(tool_name)
        
        if not func:
            print(f"[ERROR] Tool '{tool_name}' not found in registry.")
            return

        try:
            # We unpack the dictionary as keyword arguments (**args)
            # This allows the LLM to provide 'level=50' or 'app_name="Chrome"' dynamically
            result = func(**args)
            
            # 3. FEEDBACK
            status_icon = "[OK]" if result.get("status") == "success" else "[WARN]"
            print(f"{status_icon} Result: {result}")
            
        except TypeError as e:
            print(f"[ERROR] Argument Mismatch: The LLM provided wrong arguments for {tool_name}. ({e})")
        except Exception as e:
            print(f"[ERROR] Execution Crash: {e}")

# --- TEST COMMANDS ---
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

# --- RUN LOOP ---
if __name__ == "__main__":
    agent = LocalAgent()

    print("[AGENT] Local Agent Initialized.")
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