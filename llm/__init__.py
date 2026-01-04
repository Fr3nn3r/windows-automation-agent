"""
LLM adapters for the Windows Automation Agent.

Provides adapters for different LLM providers that implement
the LLMClient protocol.
"""

from llm.groq_adapter import GroqAdapter
from llm.mock_adapter import MockLLMAdapter

__all__ = [
    "GroqAdapter",
    "MockLLMAdapter",
]
