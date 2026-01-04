"""
Dynamic prompt builder for the Windows Automation Agent.

Generates the tools specification section of the system prompt
from the registered tools.

Following Open/Closed Principle (OCP): new tools are automatically
included in the prompt without code changes.
"""

from typing import List

from core.tool_decorator import get_registered_tools


def build_tools_prompt() -> str:
    """
    Dynamically generate tool specs from the registry.

    Returns:
        Formatted string with all tool specifications
    """
    lines = ["Tools and their EXACT argument names:"]

    for name, (_, spec) in get_registered_tools().items():
        # Format args
        if spec.args_schema:
            args_parts = []
            for arg_name, arg_type in spec.args_schema.items():
                args_parts.append(f'"{arg_name}": <{arg_type}>')
            args_str = ", ".join(args_parts)
            args_display = f"{{args: {{{args_str}}}}}"
        else:
            args_display = "{args: {}}"

        # Add destructive marker if applicable
        suffix = " [DESTRUCTIVE]" if spec.destructive else ""

        # Add description if provided
        desc = f" -> {spec.description}" if spec.description else ""

        lines.append(f"- {name}: {args_display}{desc}{suffix}")

    return "\n".join(lines)


def build_tool_list() -> List[str]:
    """
    Get a simple list of available tool names.

    Returns:
        List of tool names
    """
    return list(get_registered_tools().keys())
