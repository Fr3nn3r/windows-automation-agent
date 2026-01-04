"""
Constants and configuration for the Windows Automation Agent.

Centralized location for:
- Destructive action definitions
- Latency injection configuration
- Model configuration
"""

from typing import Dict, Any

# =============================================================================
# DESTRUCTIVE ACTIONS
# =============================================================================

# Actions that require user confirmation before execution
DESTRUCTIVE_ACTIONS: Dict[str, Dict[str, Any]] = {
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
# LATENCY INJECTION
# =============================================================================

# Tools that need latency injection (wait for UI to appear)
LATENCY_TOOLS: Dict[str, float] = {
    "open_explorer": 1.0,   # Wait 1s for Explorer window
    "focus_window": 0.3,    # Brief wait for focus change
}


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

# Groq model identifiers
MODEL_FAST = "llama-3.1-8b-instant"      # The Intern - fast but limited
MODEL_SMART = "llama-3.1-70b-versatile"  # The Senior - slower but smarter

# Context limits
MAX_CONTEXT_TOKENS = 8192  # Groq Llama models context window
MAX_OUTPUT_TOKENS = 512    # Keep output concise for context limits

# Short-term memory size (number of turns to keep)
SHORT_TERM_MEMORY_SIZE = 2
