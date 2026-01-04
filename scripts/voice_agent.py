"""
Voice Agent for Windows Automation.

Uses Pipecat + Gemini 2.0 Flash Live for voice-to-voice interaction.
All tools from ToolRegistry are available for voice commands.
"""

import asyncio
import json
import logging
import os
import struct
import sys
from datetime import datetime
from typing import Any, Dict

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import LocalAgent
from voice_tools_config import get_voice_tools_definition

load_dotenv()

# =============================================================================
# LOGGING SETUP
# =============================================================================

# Configure logging to show both pipecat and tool execution logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%H:%M:%S",
)

# Create logger for tool execution
tool_logger = logging.getLogger("tools.execution")
tool_logger.setLevel(logging.INFO)

# Pipecat loggers
pipecat_logger = logging.getLogger("pipecat")
pipecat_logger.setLevel(logging.INFO)


def log_tool_call(tool_name: str, args: Dict[str, Any], result: Any, duration_ms: float) -> None:
    """Log a tool execution with formatted output."""
    args_str = json.dumps(args, default=str) if args else "{}"

    # Format result for logging (truncate if too long)
    if isinstance(result, dict):
        result_str = json.dumps(result, default=str)
        if len(result_str) > 200:
            result_str = result_str[:200] + "..."
    else:
        result_str = str(result)[:200]

    status = "OK" if isinstance(result, dict) and result.get("status") == "success" else "DONE"

    tool_logger.info(
        f"[TOOL] {tool_name}({args_str}) -> {status} ({duration_ms:.1f}ms)"
    )
    tool_logger.debug(f"[TOOL] Result: {result_str}")


# =============================================================================
# PIPECAT IMPORTS (deferred to allow logging setup first)
# =============================================================================

from pipecat.frames.frames import AudioRawFrame, Frame, InputAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.services.google.gemini_live import GeminiLiveLLMService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams


# =============================================================================
# AUDIO MONITOR (for debugging)
# =============================================================================

class AudioLevelMonitor(FrameProcessor):
    """Monitor audio levels to debug microphone input."""

    def __init__(self, log_interval: int = 100):
        super().__init__()
        self._frame_count = 0
        self._log_interval = log_interval
        self._logger = logging.getLogger("audio.monitor")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, (AudioRawFrame, InputAudioRawFrame)):
            self._frame_count += 1
            if self._frame_count % self._log_interval == 0:
                # Calculate RMS level
                samples = struct.unpack(f"{len(frame.audio) // 2}h", frame.audio)
                rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                self._logger.debug(f"Frame {self._frame_count}, RMS: {rms:.0f}")

        await self.push_frame(frame, direction)


# =============================================================================
# TOOL EXECUTOR (Router-Solver Pattern)
# =============================================================================

class VoiceToolExecutor:
    """
    Bridge between Gemini (Voice Router) and LocalAgent (Logic Solver).

    Router-Solver Pattern:
    - Gemini handles voice I/O and decides WHEN to act
    - LocalAgent (Groq/Llama-3) handles WHAT tool to use

    This decouples the unreliable voice interface from the reliable logic engine.
    """

    def __init__(self):
        """Initialize the Logic Engine (LocalAgent with Groq)."""
        self._logger = logging.getLogger("tools.executor")
        print("[Init] Waking up the Groq Logic Engine...")
        self.logic_engine = LocalAgent()

    def execute(self, function_name: str, tool_call_id: str, args: Dict[str, Any]) -> str:
        """
        The Bridge: Gemini (Voice) -> execute -> Groq (Logic) -> Tool

        Args:
            function_name: Should be 'computer_terminal'
            tool_call_id: Gemini's ID for this tool call
            args: Should contain 'command' with user's natural language request

        Returns:
            String result for Gemini to speak
        """
        command = args.get("command", "")
        start_time = datetime.now()

        print(f"\n⚡ [Gemini Handoff] -> Groq: '{command}'")
        self._logger.info(f">>> Voice Command: {command}")

        if not command:
            return "No command received"

        try:
            # Ask the LocalAgent (Groq) to handle the command
            # This reuses our robust tool selection logic
            result = self.logic_engine.execute(command)

            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_tool_call("computer_terminal", args, result, duration_ms)

            # Simplify the output so Gemini doesn't read raw JSON
            if isinstance(result, dict):
                if result.get("status") == "success":
                    # Return clean message for Gemini to speak
                    return result.get("message", "Done.")
                else:
                    return f"Error: {result.get('message', 'Unknown error')}"
            else:
                return str(result)

        except Exception as e:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            self._logger.error(f"    Error: {e}")
            log_tool_call("computer_terminal", args, {"status": "error", "message": str(e)}, duration_ms)
            return f"Error: {str(e)}"

    async def handle_function_call(self, params) -> None:
        """
        Async handler for pipecat function calls.

        CRITICAL: Execution runs in a thread pool to avoid blocking
        the async audio pipeline (websocket desync with Gemini).

        Args:
            params: FunctionCallParams with function_name, tool_call_id, arguments
        """
        function_name = params.function_name
        tool_call_id = params.tool_call_id
        arguments = dict(params.arguments) if params.arguments else {}

        print(f"⚡ [Gemini Trigger] {function_name}({arguments})")

        # Run blocking execution in thread pool to keep audio alive
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.execute(function_name, tool_call_id, arguments)
        )

        await params.result_callback(result)


# =============================================================================
# MAIN VOICE AGENT
# =============================================================================

async def main():
    """Run the voice agent."""

    print("\n" + "=" * 60)
    print("  WINDOWS VOICE AUTOMATION AGENT")
    print("=" * 60 + "\n")

    # Check for API keys
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not found in environment")
        print("Please add GOOGLE_API_KEY=your_key to your .env file")
        return

    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("WARNING: GROQ_API_KEY not found. LocalAgent will run in MOCK mode.")

    # Initialize the Voice Tool Executor (contains LocalAgent/Groq logic engine)
    executor = VoiceToolExecutor()

    # Load single-tool Gemini definition (Router-Solver pattern)
    print("[Init] Loading Voice Tool Definition (computer_terminal)...")
    tools_def = get_voice_tools_definition()
    print("[Init] Gemini will route ALL commands to LocalAgent (Groq)")
    print()

    # 1. Audio Transport with VAD
    print("[Init] Setting up audio transport...")
    vad = SileroVADAnalyzer(
        params=VADParams(
            confidence=0.7,      # Higher = needs more confidence
            start_secs=0.2,      # Wait before detecting speech start
            stop_secs=0.5,       # Wait after speech stops
            min_volume=0.6,      # Volume threshold
        )
    )
    transport = LocalAudioTransport(
        params=LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            vad_analyzer=vad,
        )
    )

    # 2. System instruction - Proxy prompt (forces tool usage)
    system_instruction = """You are a Voice Interface for a Windows PC.

CRITICAL CONSTRAINT:
- You have NO internal ability to control the computer.
- You CANNOT open folders, minimize windows, or check system info yourself.
- You MUST use the 'computer_terminal' tool for EVERY request that implies an action.

BEHAVIOR:
1. Listen to the user.
2. Immediately call 'computer_terminal' with their exact request.
3. Wait for the tool output.
4. Speak the result concisely (3-5 words max).

Example:
User: "Open the downloads folder."
You: [Call computer_terminal(command="Open the downloads folder")]
Tool Output: "Opened Explorer at C:/Users/.../Downloads"
You: "Downloads folder opened."

Example:
User: "What windows are open?"
You: [Call computer_terminal(command="What windows are open")]
Tool Output: "1. Chrome, 2. Notepad, 3. Explorer"
You: "You have Chrome, Notepad, and Explorer open."

NEVER claim to do something without calling the tool first."""

    # 3. Create LLM context with system message
    print("[Init] Creating LLM context...")
    context = OpenAILLMContext(
        messages=[{"role": "system", "content": system_instruction}],
        tools=tools_def
    )

    # 4. Gemini Live LLM with Tools
    print("[Init] Connecting to Gemini Live...")
    llm = GeminiLiveLLMService(
        api_key=api_key,
        model="models/gemini-2.0-flash-exp",
        voice_id="Puck",  # Voices: Puck, Charon, Kore, Fenrir, Aoede
        tools=tools_def,
        system_instruction=system_instruction,
    )

    # 5. Register the tool handler (catch-all handler for all functions)
    llm.register_function(None, executor.handle_function_call)

    # 6. Create context aggregators for proper message handling
    context_aggregator = llm.create_context_aggregator(context)

    # 7. Build the pipeline with context aggregators
    audio_monitor = AudioLevelMonitor(log_interval=200)
    pipeline = Pipeline([
        transport.input(),
        audio_monitor,
        context_aggregator.user(),
        llm,
        context_aggregator.assistant(),
        transport.output(),
    ])

    # 8. Run
    runner = PipelineRunner()
    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True)
    )

    print("\n" + "-" * 60)
    print("  Voice Agent Ready! (Router-Solver Mode)")
    print("-" * 60)
    print("\nArchitecture: Gemini (Voice) -> Groq (Logic) -> Tools")
    print("\nTry saying:")
    print('  - "Open Notepad"')
    print('  - "What windows are open?"')
    print('  - "Open the downloads folder"')
    print('  - "Switch to desktop 2"')
    print('  - "Minimize all windows"')
    print("\nPress Ctrl+C to stop.")
    print("-" * 60 + "\n")

    try:
        await runner.run(task)
    except KeyboardInterrupt:
        print("\n[Shutdown] Voice agent stopped by user")
    except Exception as e:
        logging.error(f"Voice agent error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
