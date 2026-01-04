import asyncio
import os
import struct

from dotenv import load_dotenv
load_dotenv()

from pipecat.frames.frames import AudioRawFrame, Frame, InputAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.services.google.gemini_live import GeminiLiveLLMService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams


class AudioLevelMonitor(FrameProcessor):
    """Monitor audio levels to debug microphone input."""

    def __init__(self):
        super().__init__()
        self._frame_count = 0
        self._logged_types = set()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Log frame types we haven't seen before
        frame_type = type(frame).__name__
        if frame_type not in self._logged_types:
            print(f"[Debug] New frame type: {frame_type}", flush=True)
            self._logged_types.add(frame_type)

        if isinstance(frame, (AudioRawFrame, InputAudioRawFrame)):
            self._frame_count += 1
            # Calculate RMS level
            samples = struct.unpack(f"{len(frame.audio) // 2}h", frame.audio)
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
            if self._frame_count % 50 == 0:  # Log every 50 frames
                print(f"[Audio] Frame {self._frame_count}, RMS level: {rms:.0f}", flush=True)

        await self.push_frame(frame, direction)

async def main():
    # 1. Transport: Use your Laptop's Mic/Speaker directly
    # VAD tuned to reduce false triggers from speaker echo
    vad = SileroVADAnalyzer(
        params=VADParams(
            confidence=0.8,      # Higher = needs more confidence (default 0.7)
            start_secs=0.3,      # Longer before detecting speech start (default 0.2)
            stop_secs=1.2,       # Longer silence before stopping (default 0.8)
            min_volume=0.8,      # Higher volume threshold (default 0.6)
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

    # 2. The Model: Gemini 2.0 Flash Experimental (Native Audio)
    # This handles STT, LLM, and TTS all in one go.
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model="models/gemini-2.0-flash-exp",
        voice_id="Puck"  # Voices: Puck, Charon, Kore, Fenrir, Aoede
    )

    # 3. Pipeline: Audio In -> Monitor -> Gemini -> Audio Out
    audio_monitor = AudioLevelMonitor()
    pipeline = Pipeline(
        [
            transport.input(),
            audio_monitor,
            llm,
            transport.output(),
        ]
    )

    # 4. Run it
    runner = PipelineRunner()
    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=False))

    print("Agent starting... speak now!")
    await runner.run(task)

if __name__ == "__main__":
    asyncio.run(main())