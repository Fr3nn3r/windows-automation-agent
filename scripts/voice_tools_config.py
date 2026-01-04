"""
Single "catch-all" tool for Voice Agent.

Router-Solver Pattern:
- Voice Layer (Gemini/Deepgram): Handles voice I/O, passes commands to the tool
- Logic Layer (LocalAgent/Groq): Handles actual tool selection and execution

This pattern plays to strengths of both models:
- Voice layer handles audio I/O with low latency
- Groq/Llama-3 is a precise tool caller
"""

# Tool description shared by all formats
TOOL_NAME = "computer_terminal"
TOOL_DESCRIPTION = (
    "The ONLY way to control the computer. Use this for ANY request involving "
    "windows, files, apps, screen, brightness, or system info. "
    "Pass the user's exact spoken request."
)
COMMAND_DESCRIPTION = (
    "The exact natural language request from the user "
    "(e.g. 'Open downloads', 'Minimize chrome', 'What windows are open')."
)


def get_voice_tools_definition():
    """
    Returns tool definition in Gemini format.

    Used by voice_agent.py (Gemini Live).
    """
    return [{
        "function_declarations": [
            {
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "command": {
                            "type": "STRING",
                            "description": COMMAND_DESCRIPTION
                        }
                    },
                    "required": ["command"]
                }
            }
        ]
    }]


def get_openai_tools_definition():
    """
    Returns tool definition in OpenAI function calling format.

    Used by reliable_voice_agent.py (Deepgram + Groq).
    Compatible with any OpenAI-compatible API (Groq, OpenAI, etc.)
    """
    return [{
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": COMMAND_DESCRIPTION
                    }
                },
                "required": ["command"]
            }
        }
    }]
