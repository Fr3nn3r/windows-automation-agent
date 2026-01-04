"""
ToolRegistry - The Body for the Windows Automation Agent.

Stateless tool executor that maps tool names to functions.
Implements the ToolExecutor protocol.
"""

from typing import Dict, Callable, Optional, List

from tools.hardware_tools import HardwareController
from tools.windows_tools import WindowManager
from tools.system_tools import SystemTools


class ToolRegistry:
    """
    Stateless tool executor - the 'Body'.
    Maps tool names to functions and executes them.

    Implements the ToolExecutor protocol.
    """

    def __init__(self):
        """Initialize the tool registry with all available tools."""
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
            "minimize_all": self.windows.minimize_all,
            "restore_all": self.windows.restore_all,
            "maximize_all": self.windows.maximize_all,
            "close_window": self.windows.close_window,
            "list_desktops": self.windows.list_desktops,
            "switch_desktop": self.windows.switch_desktop,
            "move_window": self.windows.move_window_to_desktop,

            # --- Text Input ---
            "type_text": self.windows.type_text,

            # --- System ---
            "list_files": self.system.list_directory,
            "get_sys_info": self.system.get_system_info,
            "check_processes": self.system.list_processes,
            "delete_item": self.system.delete_item,
            "get_env": self.system.get_environment_variable,
            "list_usb": self.system.list_usb_devices,
            "change_dir": self.system.change_directory,

            # --- App Launcher & Clipboard ---
            "launch_app": self.windows.launch_app,
            "open_explorer": self.system.open_explorer,
            "get_clipboard": self.system.get_clipboard,
            "set_clipboard": self.system.set_clipboard,
        }

    def get(self, tool_name: str) -> Optional[Callable]:
        """
        Get a tool function by name.

        Args:
            tool_name: The registered name of the tool

        Returns:
            The callable tool function, or None if not found
        """
        return self._registry.get(tool_name)

    def list_tools(self) -> List[str]:
        """
        List all available tool names.

        Returns:
            List of registered tool names
        """
        return list(self._registry.keys())

    def register(self, name: str, func: Callable) -> None:
        """
        Register a new tool.

        Args:
            name: The name to register the tool under
            func: The callable to execute
        """
        self._registry[name] = func

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool.

        Args:
            name: The name of the tool to remove

        Returns:
            True if the tool was removed, False if it wasn't found
        """
        if name in self._registry:
            del self._registry[name]
            return True
        return False
