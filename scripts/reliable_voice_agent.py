"""
Reliable Voice Agent for Windows Automation.

Uses the "Voice Gateway" architecture (Router-Solver pattern):
- Ear/Mouth (Deepgram): Handles STT/TTS with low latency
- Brain (Groq + Llama-3): Handles tool decisions reliably

This stack separates concerns for better reliability:
- Deepgram handles audio I/O and VAD
- Groq handles tool calling (Llama-3-70B has excellent function calling)

Prerequisites:
    pip install pipecat-ai[deepgram,openai]
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from loguru import logger

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import LocalAgent
from voice_tools_config import get_openai_tools_definition

load_dotenv()

# Configure loguru
logger.remove()  # Remove default handler
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}",
    level="INFO"
)

# Pipecat imports
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams


class VoiceToolExecutor:
    """
    Bridge between Voice Layer (Deepgram) and Logic Layer (Groq/LocalAgent).

    Router-Solver Pattern:
    - Deepgram handles audio I/O
    - This executor bridges to LocalAgent which handles tool selection
    """

    def __init__(self):
        """Initialize the Logic Engine (LocalAgent with Groq)."""
        logger.info("Initializing Groq Logic Engine...")
        self.logic_engine = LocalAgent(use_smart_model=True)  # Use 70B for voice
        logger.success("Logic Engine ready")

    def execute(self, function_name: str, tool_call_id: str, args: dict[str, Any]) -> str:
        """
        Execute a tool call by delegating to LocalAgent.

        Args:
            function_name: Should be 'computer_terminal'
            tool_call_id: The tool call ID
            args: Should contain 'command' with user's natural language request

        Returns:
            String result for TTS to speak
        """
        command = args.get("command", "")
        start_time = datetime.now()

        logger.info(f"Voice Command: '{command}'")

        if not command:
            return "No command received"

        try:
            # Delegate to LocalAgent (Groq) for tool selection and execution
            result = self.logic_engine.execute(command)

            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"Executed in {duration_ms:.0f}ms")

            # Return clean message for TTS
            if isinstance(result, dict):
                if result.get("status") == "success":
                    return result.get("message", "Done.")
                else:
                    return f"Error: {result.get('message', 'Unknown error')}"
            else:
                return str(result)

        except Exception as e:
            logger.error(f"Execution error: {e}")
            return f"Error: {str(e)}"

    async def handle_function_call(self, params) -> None:
        """
        Async handler for function calls from Pipecat.

        Runs in thread pool to avoid blocking the audio pipeline.

        Args:
            params: FunctionCallParams with function_name, tool_call_id, arguments, result_callback
        """
        function_name = params.function_name
        tool_call_id = params.tool_call_id
        arguments = dict(params.arguments) if params.arguments else {}

        logger.info(f"Function call: {function_name}({arguments})")

        # Run blocking execution in thread pool
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.execute(function_name, tool_call_id, arguments)
        )

        await params.result_callback(result)


async def main():
    """Run the reliable voice agent."""

    logger.info("Starting Reliable Voice Agent (Deepgram + Groq)")

    # Check for required API keys
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    if not deepgram_key:
        logger.error("DEEPGRAM_API_KEY not found in environment")
        logger.info("Get a free key at: https://console.deepgram.com/")
        return

    if not groq_key:
        logger.warning("GROQ_API_KEY not found. LocalAgent will run in MOCK mode.")

    # 1. Initialize the Tool Executor (contains LocalAgent)
    executor = VoiceToolExecutor()

    # 2. Get tool definitions in OpenAI format
    tools = get_openai_tools_definition()

    # 3. Services (The Modular Stack)

    # EAR: Deepgram STT (fastest transcription available)
    stt = DeepgramSTTService(
        api_key=deepgram_key,
        model="nova-2",  # Latest model with best accuracy
    )

    # BRAIN: Groq (Llama 3.3 70B via OpenAI-compatible API)
    # This is the "Solver" - receives text, outputs reliable tool calls
    llm = OpenAILLMService(
        api_key=groq_key,
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
    )

    # MOUTH: Deepgram TTS (low latency voice)
    tts = DeepgramTTSService(
        api_key=deepgram_key,
        voice="aura-asteria-en",  # High quality, low latency
    )

    # 4. Audio Transport with VAD
    # Tuned settings for snappy interruptions
    vad = SileroVADAnalyzer(
        params=VADParams(
            confidence=0.7,      # Speech detection confidence
            start_secs=0.2,      # Wait before speech start
            stop_secs=0.4,       # Stop listening quickly after pause
            min_volume=0.6,      # Volume threshold
        )
    )
    transport = LocalAudioTransport(
        params=LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=vad,
        )
    )

    # 5. LLM Context with System Prompt
    system_prompt = """You are a Windows Automation Assistant.

BEHAVIOR:
- You are a precise execution engine.
- You MUST call the 'computer_terminal' tool when the user requests an action.
- If the user says "Open Downloads", call computer_terminal with that command.
- If the user says "What windows are open?", call computer_terminal with that command.
- Be concise. Response length: 1 sentence max after tool execution.

EXAMPLES:
User: "Open Notepad"
-> Call computer_terminal(command="Open Notepad")
-> Say: "Notepad opened."

User: "Minimize all windows"
-> Call computer_terminal(command="Minimize all windows")
-> Say: "Done."

User: "What's my brightness?"
-> Call computer_terminal(command="What is the current brightness?")
-> Say: "Brightness is 50 percent."

NEVER claim to do something without calling computer_terminal first."""

    messages = [{"role": "system", "content": system_prompt}]
    context = OpenAILLMContext(messages=messages, tools=tools)
    context_aggregator = llm.create_context_aggregator(context)

    # 6. Register Tool Handler (catch-all handler)
    # Using None as function name registers for all functions
    llm.register_function(None, executor.handle_function_call)

    # 7. Build the Pipeline
    pipeline = Pipeline([
        transport.input(),       # Microphone
        stt,                     # Speech -> Text
        context_aggregator.user(),
        llm,                     # Text -> Decision (tool calls)
        context_aggregator.assistant(),
        tts,                     # Text -> Speech
        transport.output(),      # Speaker
    ])

    # 8. Run
    runner = PipelineRunner()
    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True)
    )

    print("\n" + "=" * 60)
    print("  RELIABLE VOICE AGENT")
    print("  Stack: Deepgram (STT/TTS) + Groq (Llama-3.3-70B)")
    print("=" * 60)
    print("\nThis stack prioritizes Tool Calling Reliability.")
    print("\nTry saying:")
    print('  - "Open Notepad"')
    print('  - "What windows are open?"')
    print('  - "Open the downloads folder"')
    print('  - "Minimize all windows"')
    print('  - "Set brightness to 50 percent"')
    print("\nPress Ctrl+C to stop.")
    print("=" * 60 + "\n")

    try:
        await runner.run(task)
    except KeyboardInterrupt:
        logger.info("Voice agent stopped by user")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
