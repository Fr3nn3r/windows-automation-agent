"""
Groq LLM adapter.

Wraps the Groq client to implement the LLMClient protocol.
"""

import json
import time
from typing import List, Dict, Any, Optional

from groq import Groq

from core.constants import MODEL_FAST, MODEL_SMART, MAX_OUTPUT_TOKENS


class GroqAdapter:
    """
    Adapter for Groq LLM API.

    Implements the LLMClient protocol for use with the Brain.

    Two-Gear Strategy:
    - 8B (default): Fast (~1200 t/s), good for simple commands
    - 70B (fallback): Smarter (~300 t/s), for complex reasoning
    """

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        use_smart_model: bool = False
    ):
        """
        Initialize the Groq adapter.

        Args:
            api_key: Groq API key
            model: Optional specific model to use
            use_smart_model: If True, use 70B model; otherwise use 8B
        """
        self.client = Groq(api_key=api_key)
        self.model = model or (MODEL_SMART if use_smart_model else MODEL_FAST)

    def complete(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, str]] = None,
        temperature: float = 0.0,
        max_tokens: int = MAX_OUTPUT_TOKENS,
        **kwargs
    ) -> str:
        """
        Send messages to Groq and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            response_format: Optional format specification (e.g., {"type": "json_object"})
            temperature: Sampling temperature (0.0 for deterministic)
            max_tokens: Maximum tokens in response
            **kwargs: Additional Groq-specific options

        Returns:
            The LLM's response as a string
        """
        start = time.time()

        completion_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        if response_format:
            completion_kwargs["response_format"] = response_format

        completion = self.client.chat.completions.create(**completion_kwargs)

        latency = (time.time() - start) * 1000
        response_text = completion.choices[0].message.content

        print(f"[LLM] Response ({latency:.0f}ms): {response_text[:100]}...")

        return response_text

    def complete_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = MAX_OUTPUT_TOKENS,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send messages and get a JSON response.

        Convenience method that sets response_format to json_object
        and parses the response.

        Args:
            messages: List of message dicts
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional options

        Returns:
            Parsed JSON as a dict
        """
        response = self.complete(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        return json.loads(response)
