"""
Constants and configuration for the Windows Automation Agent.

Centralized location for:
- Latency injection configuration
- Model configuration

Note: Destructive actions are now defined declaratively in tools/tool_specs.py
via the ToolSpec.destructive and ToolSpec.risk_level attributes.
Use core.tool_decorator.get_destructive_tools() to retrieve them at runtime.
"""

from typing import Dict

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
