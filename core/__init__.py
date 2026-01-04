"""
Core module for Windows Automation Agent.

This module contains the core abstractions and implementations
for the agent architecture following SOLID principles.
"""

from core.protocols import LLMClient, DecisionMaker, ToolExecutor, StateManager, SafetyGate
from core.context import AgentContext, ConversationTurn
from core.constants import DESTRUCTIVE_ACTIONS, LATENCY_TOOLS, MODEL_FAST, MODEL_SMART
from core.brain import Brain
from core.registry import ToolRegistry
from core.router import Router
from core.agent import LocalAgent
from core.tool_decorator import tool, ToolSpec, get_registered_tools

__all__ = [
    # Protocols
    "LLMClient",
    "DecisionMaker",
    "ToolExecutor",
    "StateManager",
    "SafetyGate",
    # Context
    "AgentContext",
    "ConversationTurn",
    # Constants
    "DESTRUCTIVE_ACTIONS",
    "LATENCY_TOOLS",
    "MODEL_FAST",
    "MODEL_SMART",
    # Core classes
    "Brain",
    "ToolRegistry",
    "Router",
    "LocalAgent",
    # Tool decorator
    "tool",
    "ToolSpec",
    "get_registered_tools",
]
