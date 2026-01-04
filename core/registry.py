"""
ToolRegistry - The Body for the Windows Automation Agent.

Stateless tool executor that maps tool names to functions.
Implements the ToolExecutor protocol.

Following Open/Closed Principle (OCP): tools are registered via
the declarative specs in tools/tool_specs.py, not hardcoded here.
"""

from typing import Callable, Optional, List

from tools.hardware_tools import HardwareController
from tools.windows_tools import WindowManager
from tools.system_tools import SystemTools
from tools.tool_specs import register_all_tools
from core.tool_decorator import get_tool_func, list_tool_names


class ToolRegistry:
    """
    Stateless tool executor - the 'Body'.
    Maps tool names to functions and executes them.

    Implements the ToolExecutor protocol.

    Tools are registered declaratively via tools/tool_specs.py,
    making it easy to add/modify tools without changing this class.
    """

    def __init__(self):
        """Initialize the tool registry with all available tools."""
        # Create tool class instances
        self.hardware = HardwareController()
        self.windows = WindowManager()
        self.system = SystemTools()

        # Register all tools using declarative specs
        # This populates the global tool registry
        register_all_tools(
            hardware_controller=self.hardware,
            window_manager=self.windows,
            system_tools=self.system
        )

    def get(self, tool_name: str) -> Optional[Callable]:
        """
        Get a tool function by name.

        Args:
            tool_name: The registered name of the tool

        Returns:
            The callable tool function, or None if not found
        """
        return get_tool_func(tool_name)

    def list_tools(self) -> List[str]:
        """
        List all available tool names.

        Returns:
            List of registered tool names
        """
        return list_tool_names()
