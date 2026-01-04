"""
Mock LLM adapter for testing without API key.

Provides pattern-based responses that simulate LLM behavior
for development and testing purposes.
"""

import re
import json
from typing import List, Dict, Any


class MockLLMAdapter:
    """
    Mock adapter for testing without an actual LLM.

    Implements the LLMClient protocol using pattern matching
    to simulate LLM responses.
    """

    def complete(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """
        Return a mock response based on the last user message.

        Args:
            messages: List of message dicts
            **kwargs: Ignored

        Returns:
            JSON string with tool decision
        """
        # Find the last user message
        user_input = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_input = msg.get("content", "")
                break

        decision = self._mock_decide(user_input)
        return json.dumps(decision)

    def _mock_decide(self, user_input: str) -> Dict[str, Any]:
        """
        Mock decision logic for testing without API key.

        Pattern-based matching to simulate LLM tool selection.
        """
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

        # Type text command
        if "type" in user_lower:
            match = re.search(r"['\"]([^'\"]+)['\"]", user_input)
            if match:
                return {"tool": "type_text", "args": {"text": match.group(1)}}

        return {"tool": "error", "args": {"message": "Mock mode: Unknown command"}}
