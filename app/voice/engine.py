"""Speech-to-text + speaker-embedding engine (lazy-loaded).

A single audio upload is decoded once into a 16kHz mono float32 waveform and
fed to both:
  - faster-whisper  -> transcript (Chinese by default)
  - Resemblyzer     -> a 256-dim speaker embedding (the "voiceprint")

All heavy imports happen lazily inside ``_ensure_loaded`` so that importing this
module (or running the rest of the app) never pulls in torch / whisper.
"""

from __future__ import annotations

import io
import threading

import numpy as np

from app.config import settings


class VoiceUnavailable(RuntimeError):
    """Raised when voice deps are missing or disabled, so callers can 503."""


class VoiceEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._whisper = None
        self._encoder = None
        self._decode_audio = None
        self._preprocess_wav = None

    def _ensure_loaded(self) -> None:
        if not settings.voice_enabled:
            raise VoiceUnavailable("voice is disabled (set VOICE_ENABLED=1 to enable)")
        if self._whisper is not None and self._encoder is not None:
            return
        with self._lock:
            if self._whisper is not None and self._encoder is not None:
                return
            try:
                from faster_whisper import WhisperModel
                from faster_whisper.audio import decode_audio
                from resemblyzer import VoiceEncoder, preprocess_wav
            except Exception as exc:  # pragma: no cover - import/env failure path
                raise VoiceUnavailable(
                    "voice dependencies are not installed; run "
                    "`pip install faster-whisper resemblyzer`"
                ) from exc

            try:
                self._whisper = WhisperModel(
                    settings.whisper_model,
                    device=settings.whisper_device,
                    compute_type=settings.whisper_compute_type,
                )
                self._encoder = VoiceEncoder()
            except Exception as exc:  # pragma: no cover - model load failure
                raise VoiceUnavailable(f"failed to load voice models: {exc}") from exc

            self._decode_audio = decode_audio
            self._preprocess_wav = preprocess_wav

    def process(self, audio_bytes: bytes) -> tuple[str, np.ndarray]:
        """Decode audio once, then return (transcript, speaker_embedding)."""
        self._ensure_loaded()
        if not audio_bytes:
            raise VoiceUnavailable("empty audio upload")

        try:
            wav = self._decode_audio(io.BytesIO(audio_bytes), sampling_rate=16000)
        except Exception as exc:
            raise VoiceUnavailable(f"could not decode audio: {exc}") from exc
        wav = np.asarray(wav, dtype=np.float32)

        # --- transcript -------------------------------------------------
        transcript = ""
        try:
            segments, _info = self._whisper.transcribe(
                wav, language=settings.whisper_language
            )
            transcript = "".join(seg.text for seg in segments).strip()
        except Exception:
            transcript = ""

        # --- voiceprint -------------------------------------------------
        processed = self._preprocess_wav(wav, source_sr=16000)
        embedding = self._encoder.embed_utterance(processed)
        embedding = np.asarray(embedding, dtype=np.float32)

        return transcript, embedding


engine = VoiceEngine()
