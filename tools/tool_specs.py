"""
Centralized tool specifications for the Windows Automation Agent.

This file defines all tool specs using JSON Schema format and registers
them with their implementations. This separates the "what" (specification)
from the "how" (implementation).

Benefits:
- Single source of truth for tool definitions
- LLM-friendly JSON Schema format
- Easy to add/modify tools without touching implementation
- Compatible with OpenAI/Anthropic tool calling APIs
"""

from core.tool_decorator import (
    ToolSpec,
    register_tool,
    make_schema,
    string_param,
    int_param,
    bool_param,
)

# =============================================================================
# HARDWARE TOOLS
# =============================================================================

SET_BRIGHTNESS_SPEC = ToolSpec(
    name="set_brightness",
    description="Sets the screen brightness level on all monitors",
    input_schema=make_schema(
        properties={
            "level": int_param("Brightness percentage", minimum=0, maximum=100),
        },
        required=["level"]
    ),
    returns_description="Confirmation of brightness change"
)

TURN_SCREEN_OFF_SPEC = ToolSpec(
    name="turn_screen_off",
    description="Turns off the monitor(s) by sending a power-off signal",
    input_schema=make_schema(properties={}, required=[]),
    returns_description="Confirmation that power-off signal was sent"
)

TURN_SCREEN_ON_SPEC = ToolSpec(
    name="turn_screen_on",
    description="Wakes up the monitor(s) from sleep by simulating mouse movement",
    input_schema=make_schema(properties={}, required=[]),
    returns_description="Confirmation that wake signal was sent"
)

# =============================================================================
# WINDOW MANAGEMENT TOOLS
# =============================================================================

LIST_WINDOWS_SPEC = ToolSpec(
    name="list_windows",
    description="Lists all open application windows with their IDs",
    input_schema=make_schema(properties={}, required=[]),
    returns_description='Numbered list like "1. Notepad", "2. Chrome". Use IDs for other window commands.'
)

FOCUS_WINDOW_SPEC = ToolSpec(
    name="focus_window",
    description="Brings a window to the foreground and gives it focus",
    input_schema=make_schema(
        properties={
            "window_id": string_param("Window ID (number) or partial title to match"),
        },
        required=["window_id"]
    ),
)

MINIMIZE_WINDOW_SPEC = ToolSpec(
    name="minimize_window",
    description="Minimizes a specific window to the taskbar",
    input_schema=make_schema(
        properties={
            "window_id": string_param("Window ID (number) or partial title to match"),
        },
        required=["window_id"]
    ),
)

MINIMIZE_ALL_SPEC = ToolSpec(
    name="minimize_all",
    description="Minimizes all windows, optionally filtered by app name",
    input_schema=make_schema(
        properties={
            "filter_name": string_param("Optional app name filter (e.g., 'chrome', 'notepad')"),
        },
        required=[]
    ),
)

RESTORE_ALL_SPEC = ToolSpec(
    name="restore_all",
    description="Restores all previously minimized windows",
    input_schema=make_schema(properties={}, required=[]),
)

MAXIMIZE_ALL_SPEC = ToolSpec(
    name="maximize_all",
    description="Maximizes all windows on the current desktop",
    input_schema=make_schema(properties={}, required=[]),
)

CLOSE_WINDOW_SPEC = ToolSpec(
    name="close_window",
    description="Closes a window (may cause data loss if unsaved)",
    input_schema=make_schema(
        properties={
            "window_id": string_param("Window ID (number) or partial title to match"),
        },
        required=["window_id"]
    ),
    destructive=True,
    risk_level="MEDIUM",
    target_key="window_id"
)

# =============================================================================
# VIRTUAL DESKTOP TOOLS
# =============================================================================

LIST_DESKTOPS_SPEC = ToolSpec(
    name="list_desktops",
    description="Lists all virtual desktops and indicates the current one",
    input_schema=make_schema(properties={}, required=[]),
    returns_description="List of virtual desktops with current desktop marked"
)

SWITCH_DESKTOP_SPEC = ToolSpec(
    name="switch_desktop",
    description="Switches to a different virtual desktop by index (1-based)",
    input_schema=make_schema(
        properties={
            "index": int_param("Desktop number (1-based)", minimum=1),
        },
        required=["index"]
    ),
)

MOVE_WINDOW_SPEC = ToolSpec(
    name="move_window",
    description="Moves a window to a different virtual desktop",
    input_schema=make_schema(
        properties={
            "window_id": string_param("Window ID (number) or partial title"),
            "desktop_index": int_param("Target desktop number (1-based)", minimum=1),
        },
        required=["window_id", "desktop_index"]
    ),
)

# =============================================================================
# TEXT INPUT TOOLS
# =============================================================================

TYPE_TEXT_SPEC = ToolSpec(
    name="type_text",
    description="Types text into the currently focused window (uses clipboard for reliability)",
    input_schema=make_schema(
        properties={
            "text": string_param("The text to type"),
        },
        required=["text"]
    ),
)

# =============================================================================
# FILE SYSTEM TOOLS
# =============================================================================

LIST_FILES_SPEC = ToolSpec(
    name="list_files",
    description="Lists files and folders in a directory",
    input_schema=make_schema(
        properties={
            "path": string_param("Directory path (use ~ for home, . for current)"),
        },
        required=["path"]
    ),
    returns_description="List of files/folders with [FILE] or [DIR] prefix"
)

DELETE_ITEM_SPEC = ToolSpec(
    name="delete_item",
    description="Permanently deletes a file or folder (cannot be undone)",
    input_schema=make_schema(
        properties={
            "path": string_param("Path to the file or folder to delete"),
            "confirm": bool_param("Must be true to confirm deletion", default=False),
        },
        required=["path", "confirm"]
    ),
    destructive=True,
    risk_level="HIGH",
    target_key="path"
)

CHANGE_DIR_SPEC = ToolSpec(
    name="change_dir",
    description="Changes the current working directory",
    input_schema=make_schema(
        properties={
            "path": string_param("Target directory path (use ~ for home)"),
        },
        required=["path"]
    ),
)

# =============================================================================
# APPLICATION TOOLS
# =============================================================================

LAUNCH_APP_SPEC = ToolSpec(
    name="launch_app",
    description="Launches an application and waits for its window to appear",
    input_schema=make_schema(
        properties={
            "app_name": string_param(
                "App name or shortcut (e.g., 'notepad', 'chrome', 'calc', 'code')"
            ),
        },
        required=["app_name"]
    ),
    returns_description="Confirmation with window ID of launched app"
)

OPEN_EXPLORER_SPEC = ToolSpec(
    name="open_explorer",
    description="Opens Windows File Explorer at a specific path",
    input_schema=make_schema(
        properties={
            "path": string_param("Folder path to open (use ~ for home)"),
        },
        required=["path"]
    ),
)

# =============================================================================
# SYSTEM INFORMATION TOOLS
# =============================================================================

GET_SYS_INFO_SPEC = ToolSpec(
    name="get_sys_info",
    description="Returns system information (OS, hostname, CPU, memory usage)",
    input_schema=make_schema(properties={}, required=[]),
)

CHECK_PROCESSES_SPEC = ToolSpec(
    name="check_processes",
    description="Lists running processes, optionally filtered by name",
    input_schema=make_schema(
        properties={
            "filter_name": string_param("Optional process name filter (e.g., 'python', 'chrome')"),
        },
        required=[]
    ),
)

GET_ENV_SPEC = ToolSpec(
    name="get_env",
    description="Gets the value of an environment variable",
    input_schema=make_schema(
        properties={
            "var_name": string_param("Environment variable name (e.g., 'PATH', 'HOME')"),
        },
        required=["var_name"]
    ),
)

LIST_USB_SPEC = ToolSpec(
    name="list_usb",
    description="Lists connected USB devices",
    input_schema=make_schema(properties={}, required=[]),
)

# =============================================================================
# CLIPBOARD TOOLS
# =============================================================================

GET_CLIPBOARD_SPEC = ToolSpec(
    name="get_clipboard",
    description="Gets the current clipboard text content",
    input_schema=make_schema(properties={}, required=[]),
)

SET_CLIPBOARD_SPEC = ToolSpec(
    name="set_clipboard",
    description="Sets the clipboard content to the specified text",
    input_schema=make_schema(
        properties={
            "text": string_param("Text to copy to clipboard"),
        },
        required=["text"]
    ),
)


# =============================================================================
# REGISTRATION FUNCTION
# =============================================================================

def register_all_tools(
    hardware_controller,
    window_manager,
    system_tools
) -> None:
    """
    Register all tools with their implementations.

    This function connects the tool specifications (defined above) with
    their actual implementations from the tool classes.

    Args:
        hardware_controller: HardwareController instance
        window_manager: WindowManager instance
        system_tools: SystemTools instance
    """
    # Hardware tools
    register_tool("set_brightness", hardware_controller.set_brightness, SET_BRIGHTNESS_SPEC)
    register_tool("turn_screen_off", hardware_controller.turn_screen_off, TURN_SCREEN_OFF_SPEC)
    register_tool("turn_screen_on", hardware_controller.turn_screen_on, TURN_SCREEN_ON_SPEC)

    # Window management tools
    register_tool("list_windows", window_manager.list_open_windows, LIST_WINDOWS_SPEC)
    register_tool("focus_window", window_manager.focus_window, FOCUS_WINDOW_SPEC)
    register_tool("minimize_window", window_manager.minimize_window, MINIMIZE_WINDOW_SPEC)
    register_tool("minimize_all", window_manager.minimize_all, MINIMIZE_ALL_SPEC)
    register_tool("restore_all", window_manager.restore_all, RESTORE_ALL_SPEC)
    register_tool("maximize_all", window_manager.maximize_all, MAXIMIZE_ALL_SPEC)
    register_tool("close_window", window_manager.close_window, CLOSE_WINDOW_SPEC)

    # Virtual desktop tools
    register_tool("list_desktops", window_manager.list_desktops, LIST_DESKTOPS_SPEC)
    register_tool("switch_desktop", window_manager.switch_desktop, SWITCH_DESKTOP_SPEC)
    register_tool("move_window", window_manager.move_window_to_desktop, MOVE_WINDOW_SPEC)

    # Text input
    register_tool("type_text", window_manager.type_text, TYPE_TEXT_SPEC)

    # File system tools
    register_tool("list_files", system_tools.list_directory, LIST_FILES_SPEC)
    register_tool("delete_item", system_tools.delete_item, DELETE_ITEM_SPEC)
    register_tool("change_dir", system_tools.change_directory, CHANGE_DIR_SPEC)

    # Application tools
    register_tool("launch_app", window_manager.launch_app, LAUNCH_APP_SPEC)
    register_tool("open_explorer", system_tools.open_explorer, OPEN_EXPLORER_SPEC)

    # System information tools
    register_tool("get_sys_info", system_tools.get_system_info, GET_SYS_INFO_SPEC)
    register_tool("check_processes", system_tools.list_processes, CHECK_PROCESSES_SPEC)
    register_tool("get_env", system_tools.get_environment_variable, GET_ENV_SPEC)
    register_tool("list_usb", system_tools.list_usb_devices, LIST_USB_SPEC)

    # Clipboard tools
    register_tool("get_clipboard", system_tools.get_clipboard, GET_CLIPBOARD_SPEC)
    register_tool("set_clipboard", system_tools.set_clipboard, SET_CLIPBOARD_SPEC)


# Export all specs for potential direct use
ALL_TOOL_SPECS = [
    SET_BRIGHTNESS_SPEC,
    TURN_SCREEN_OFF_SPEC,
    TURN_SCREEN_ON_SPEC,
    LIST_WINDOWS_SPEC,
    FOCUS_WINDOW_SPEC,
    MINIMIZE_WINDOW_SPEC,
    MINIMIZE_ALL_SPEC,
    RESTORE_ALL_SPEC,
    MAXIMIZE_ALL_SPEC,
    CLOSE_WINDOW_SPEC,
    LIST_DESKTOPS_SPEC,
    SWITCH_DESKTOP_SPEC,
    MOVE_WINDOW_SPEC,
    TYPE_TEXT_SPEC,
    LIST_FILES_SPEC,
    DELETE_ITEM_SPEC,
    CHANGE_DIR_SPEC,
    LAUNCH_APP_SPEC,
    OPEN_EXPLORER_SPEC,
    GET_SYS_INFO_SPEC,
    CHECK_PROCESSES_SPEC,
    GET_ENV_SPEC,
    LIST_USB_SPEC,
    GET_CLIPBOARD_SPEC,
    SET_CLIPBOARD_SPEC,
]
