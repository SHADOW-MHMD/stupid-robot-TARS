"""
Sound Effects Player for TARS Robot.
Uses aplay / paplay to play pre-recorded WAV assets asynchronously.
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
import subprocess
import threading
from typing import Optional

logger = logging.getLogger("TARS.SoundEffects")
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds"


class SoundEffectPlayer:
    def __init__(
        self,
        device: str = "default",
        synthetic: bool = False,
        sounds_dir: Optional[Path] = None,
    ) -> None:
        self.device = str(device)
        self.synthetic = bool(synthetic)
        self.sounds_dir = Path(sounds_dir) if sounds_dir else _ASSETS_DIR

    def play_wav_async(self, filename: str) -> None:
        if self.synthetic:
            logger.debug(f"[SYNTHETIC SOUND EFFECT]: {filename}")
            return
        filepath = self.sounds_dir / filename
        if not filepath.exists():
            return
        
        def _play():
            try:
                if subprocess.run(["which", "aplay"], capture_output=True).returncode == 0:
                    subprocess.run(["aplay", "-D", self.device, "-q", str(filepath)], check=False)
                elif subprocess.run(["which", "paplay"], capture_output=True).returncode == 0:
                    subprocess.run(["paplay", str(filepath)], check=False)
            except Exception as e:
                logger.debug(f"Audio playback error: {e}")

        threading.Thread(target=_play, daemon=True).start()

    def play_pneumatic_brake(self) -> None:
        self.play_wav_async("pneumatic_brake.wav")

    def play_sonar_ping(self) -> None:
        self.play_wav_async("sonar_ping.wav")

    def play_chirp(self) -> None:
        self.play_wav_async("chirp_processing.wav")

    def play_inauguration(self) -> None:
        self.play_wav_async("inauguration_speech.wav")

    def close(self) -> None:
        pass
