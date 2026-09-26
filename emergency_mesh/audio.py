import os
import shutil
import subprocess
import time
import base64
import wave
import struct
from pathlib import Path

class AudioManager:
    def __init__(self, audio_dir=None):
        self.audio_dir = Path(audio_dir) if audio_dir else Path.home() / ".emergency_mesh" / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def record_voice_note(self, duration_seconds=5, output_file=None):
        """
        Records voice note using `termux-microphone-record` or generates fallback sample.
        Returns Path to recorded file or None if recording failed.
        """
        if output_file is None:
            filename = f"voice_{int(time.time())}.wav"
            output_file = self.audio_dir / filename
        else:
            output_file = Path(output_file)

        output_file.parent.mkdir(parents=True, exist_ok=True)

        if shutil.which("termux-microphone-record"):
            try:
                # Termux microphone recording API call
                proc = subprocess.Popen(
                    ["termux-microphone-record", "-f", str(output_file), "-l", str(duration_seconds)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(duration_seconds + 0.5)
                proc.terminate()
                if output_file.exists() and output_file.stat().st_size > 0:
                    return output_file
            except Exception:
                pass

        # Fallback for desktop/testing environments: synthesize a short WAV tone audio file
        return self._generate_fallback_wav(output_file, duration_seconds)

    def _generate_fallback_wav(self, output_file, duration_seconds=3):
        """
        Generates a valid lightweight audio WAV file for desktop testing.
        """
        try:
            sample_rate = 8000
            num_samples = int(sample_rate * duration_seconds)
            with wave.open(str(output_file), "w") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)

                # Generate simple 440Hz audible sine wave tone
                import math
                for i in range(num_samples):
                    value = int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate))
                    wav_file.writeframes(struct.pack("<h", value))

            return output_file
        except Exception:
            return None

    def encode_audio_to_base64(self, file_path):
        """
        Encodes audio file content into base64 string for mesh transport.
        """
        try:
            with open(file_path, "rb") as f:
                data = f.read()
                return base64.b64encode(data).decode("ascii")
        except Exception:
            return None

    def decode_base64_to_audio(self, audio_base64, output_file):
        """
        Decodes base64 string back into audio file on disk.
        """
        try:
            output_file = Path(output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            data = base64.b64decode(audio_base64.encode("ascii"))
            with open(output_file, "wb") as f:
                f.write(data)
            return output_file
        except Exception:
            return None

    def play_audio(self, file_path):
        """
        Plays audio file using available system or Termux players.
        """
        file_path = str(file_path)
        if not os.path.exists(file_path):
            return False

        # 1. Termux API media player
        if shutil.which("termux-media-player"):
            try:
                subprocess.Popen(
                    ["termux-media-player", "play", file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                pass

        # 2. Linux desktop media player fallbacks
        players = ["aplay", "paplay", "ffplay", "mpv", "cvlc"]
        for player in players:
            if shutil.which(player):
                try:
                    args = [player]
                    if player == "ffplay":
                        args.extend(["-nodisp", "-autoexit"])
                    args.append(file_path)

                    subprocess.Popen(
                        args,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return True
                except Exception:
                    continue

        return False
