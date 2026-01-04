"""
Dynamic prompt builder for the Windows Automation Agent.

Generates the tools specification section of the system prompt
from the registered tools using their JSON Schema definitions.

Following Open/Closed Principle (OCP): new tools are automatically
included in the prompt without code changes.
"""

from typing import List, Dict, Any

from core.tool_decorator import get_registered_tools, ToolSpec


def _format_property(name: str, prop: Dict[str, Any]) -> str:
    """Format a single property for the prompt."""
    prop_type = prop.get("type", "any")
    description = prop.get("description", "")

    # Handle enums
    if "enum" in prop:
        enum_values = ", ".join(f'"{v}"' for v in prop["enum"])
        type_str = f"one of [{enum_values}]"
    # Handle integer ranges
    elif prop_type == "integer":
        min_val = prop.get("minimum")
        max_val = prop.get("maximum")
        if min_val is not None and max_val is not None:
            type_str = f"int {min_val}-{max_val}"
        elif min_val is not None:
            type_str = f"int >= {min_val}"
        elif max_val is not None:
            type_str = f"int <= {max_val}"
        else:
            type_str = "int"
    elif prop_type == "boolean":
        default = prop.get("default")
        type_str = f"bool (default: {default})" if default is not None else "bool"
    elif prop_type == "array":
        item_type = prop.get("items", {}).get("type", "any")
        type_str = f"array of {item_type}"
    else:
        type_str = prop_type

    return f'"{name}": <{type_str}>'


def _format_tool_args(spec: ToolSpec) -> str:
    """Format the arguments section for a tool."""
    schema = spec.input_schema
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    if not properties:
        return "{}"

    args = []
    for name, prop in properties.items():
        formatted = _format_property(name, prop)
        # Mark optional args
        if name not in required:
            formatted += " (optional)"
        args.append(formatted)

    return "{" + ", ".join(args) + "}"


def build_tools_prompt() -> str:
    """
    Dynamically generate tool specs from the registry.

    Returns:
        Formatted string with all tool specifications for the LLM
    """
    tools = get_registered_tools()

    if not tools:
        return "No tools available."

    lines = ["Tools and their EXACT argument names:"]

    for name, (_, spec) in sorted(tools.items()):
        args_str = _format_tool_args(spec)

        # Build the line
        line = f"- {name}: args: {args_str}"

        # Add return description if provided
        if spec.returns_description:
            line += f" -> {spec.returns_description}"

        # Add destructive marker
        if spec.destructive:
            line += f"  [{spec.risk_level} RISK - DESTRUCTIVE]"

        lines.append(line)

    return "\n".join(lines)


def build_tool_list() -> List[str]:
    """
    Get a simple list of available tool names.

    Returns:
        List of tool names
    """
    return list(get_registered_tools().keys())


def get_tools_for_llm() -> List[Dict[str, Any]]:
    """
    Get tools in the format expected by LLM APIs (OpenAI/Anthropic style).

    Returns:
        List of tool definitions with name, description, and input_schema
    """
    tools = get_registered_tools()
    result = []

    for name, (_, spec) in tools.items():
        tool_def = {
            "name": name,
            "description": spec.description,
            "input_schema": spec.input_schema
        }
        result.append(tool_def)

    return result
