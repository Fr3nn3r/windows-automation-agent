"""
Tool decorator system for the Windows Automation Agent.

Provides a decorator-based registration system that allows tools
to be added without modifying the registry source code.

Following Open/Closed Principle (OCP): open for extension, closed for modification.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Callable, Optional, List


@dataclass
class ToolSpec:
    """
    Specification for a tool.

    Attributes:
        name: The tool's registered name
        description: Human-readable description
        args_schema: Dictionary mapping arg names to type descriptions
        destructive: Whether this tool requires confirmation
        risk_level: Risk level for destructive actions (LOW, MEDIUM, HIGH)
        target_key: For destructive actions, the key that identifies the target
    """
    name: str
    description: str
    args_schema: Dict[str, str] = field(default_factory=dict)
    destructive: bool = False
    risk_level: str = "LOW"
    target_key: Optional[str] = None


# Global registry of decorated tools
_decorated_tools: Dict[str, tuple[Callable, ToolSpec]] = {}


def tool(spec: ToolSpec):
    """
    Decorator to auto-register tools.

    Usage:
        @tool(ToolSpec(
            name="set_brightness",
            description="Sets screen brightness 0-100",
            args_schema={"level": "int 0-100"},
        ))
        def set_brightness(level: int) -> dict:
            ...

    Args:
        spec: The tool specification

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        _decorated_tools[spec.name] = (func, spec)
        return func
    return decorator


def get_registered_tools() -> Dict[str, tuple[Callable, ToolSpec]]:
    """
    Get all registered tools.

    Returns:
        Dictionary mapping tool names to (function, spec) tuples
    """
    return _decorated_tools.copy()


def get_tool(name: str) -> Optional[tuple[Callable, ToolSpec]]:
    """
    Get a specific tool by name.

    Args:
        name: The tool name

    Returns:
        (function, spec) tuple or None if not found
    """
    return _decorated_tools.get(name)


def list_tool_names() -> List[str]:
    """
    List all registered tool names.

    Returns:
        List of tool names
    """
    return list(_decorated_tools.keys())


def get_destructive_tools() -> Dict[str, Dict[str, Any]]:
    """
    Get all destructive tools with their confirmation config.

    Returns:
        Dictionary mapping tool names to their destructive config
    """
    result = {}
    for name, (_, spec) in _decorated_tools.items():
        if spec.destructive:
            result[name] = {
                "risk": spec.risk_level,
                "message": spec.description,
                "target_key": spec.target_key
            }
    return result
