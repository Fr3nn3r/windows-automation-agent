"""
Tool decorator system for the Windows Automation Agent.

Provides a decorator-based registration system that allows tools
to be added without modifying the registry source code.

Uses JSON Schema for input definitions, compatible with:
- OpenAI function calling
- Anthropic tool use
- LangChain tools

Following Open/Closed Principle (OCP): open for extension, closed for modification.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Callable, Optional, List
from functools import wraps


@dataclass
class ToolSpec:
    """
    Specification for a tool using JSON Schema format.

    Attributes:
        name: The tool's registered name (used to call the tool)
        description: Human-readable description of what the tool does
        input_schema: JSON Schema defining the input parameters
        destructive: Whether this tool requires user confirmation
        risk_level: Risk level for destructive actions (LOW, MEDIUM, HIGH)
        target_key: For destructive actions, the key that identifies the target
        returns_description: Description of what the tool returns
    """
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": []
    })
    destructive: bool = False
    risk_level: str = "LOW"
    target_key: Optional[str] = None
    returns_description: Optional[str] = None


# =============================================================================
# SCHEMA HELPERS - Make defining common parameter types easy
# =============================================================================

def string_param(description: str, enum: Optional[List[str]] = None) -> Dict[str, Any]:
    """Create a string parameter schema."""
    schema = {"type": "string", "description": description}
    if enum:
        schema["enum"] = enum
    return schema


def int_param(description: str, minimum: Optional[int] = None, maximum: Optional[int] = None) -> Dict[str, Any]:
    """Create an integer parameter schema."""
    schema = {"type": "integer", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def bool_param(description: str, default: Optional[bool] = None) -> Dict[str, Any]:
    """Create a boolean parameter schema."""
    schema = {"type": "boolean", "description": description}
    if default is not None:
        schema["default"] = default
    return schema


def array_param(description: str, item_type: str = "string") -> Dict[str, Any]:
    """Create an array parameter schema."""
    return {
        "type": "array",
        "description": description,
        "items": {"type": item_type}
    }


def make_schema(
    properties: Dict[str, Dict[str, Any]],
    required: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create a complete input schema.

    Args:
        properties: Dict mapping parameter names to their schemas
        required: List of required parameter names

    Returns:
        Complete JSON Schema object
    """
    return {
        "type": "object",
        "properties": properties,
        "required": required or []
    }


# =============================================================================
# TOOL REGISTRY
# =============================================================================

# Global registry of decorated tools
_decorated_tools: Dict[str, tuple[Callable, ToolSpec]] = {}


def tool(spec: ToolSpec):
    """
    Decorator to auto-register tools.

    Usage:
        @tool(ToolSpec(
            name="set_brightness",
            description="Sets screen brightness level",
            input_schema=make_schema(
                properties={"level": int_param("Brightness level", minimum=0, maximum=100)},
                required=["level"]
            ),
        ))
        def set_brightness(level: int) -> dict:
            ...

    Args:
        spec: The tool specification

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Store the spec on the function for introspection
        wrapper._tool_spec = spec
        _decorated_tools[spec.name] = (wrapper, spec)
        return wrapper
    return decorator


def register_tool(name: str, func: Callable, spec: ToolSpec) -> None:
    """
    Manually register a tool (for class methods or existing functions).

    Args:
        name: The tool name
        func: The callable
        spec: The tool specification
    """
    _decorated_tools[name] = (func, spec)


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


def get_tool_func(name: str) -> Optional[Callable]:
    """
    Get just the function for a tool.

    Args:
        name: The tool name

    Returns:
        The callable or None if not found
    """
    result = _decorated_tools.get(name)
    return result[0] if result else None


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


def clear_registry() -> None:
    """Clear all registered tools (useful for testing)."""
    _decorated_tools.clear()
