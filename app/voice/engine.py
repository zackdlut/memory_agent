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

    def preload(self) -> bool:
        """Eagerly load the voice models (used at server startup).

        Returns ``True`` if the models are ready, ``False`` if voice is disabled
        or the dependencies/models could not be loaded. Never raises, so the
        server can boot even when the optional voice stack is unavailable.
        """
        try:
            self._ensure_loaded()
            return True
        except VoiceUnavailable:
            return False

    def _build_initial_prompt(self, hint_names: list[str] | None) -> str | None:
        """Bias the recogniser toward proper nouns it is likely to hear.

        Feeding known people + the assistant's name as an initial prompt makes
        Whisper far more likely to transcribe those names correctly.
        """
        names = [n.strip() for n in (hint_names or []) if n and n.strip()]
        # always include the assistant's own name as a likely token
        if settings.assistant_name and settings.assistant_name not in names:
            names.append(settings.assistant_name)
        if not names:
            return None
        # cap the prompt so a huge roster doesn't crowd out the audio context
        names = names[:40]
        return "以下是可能出现的人名：" + "、".join(names) + "。"

    def process(
        self, audio_bytes: bytes, hint_names: list[str] | None = None
    ) -> tuple[str, np.ndarray]:
        """Decode audio once, then return (transcript, speaker_embedding).

        ``hint_names`` (e.g. known persona names) are folded into Whisper's
        ``initial_prompt`` to bias recognition toward those proper nouns.
        """
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
            kwargs = {
                "language": settings.whisper_language,
                "beam_size": settings.whisper_beam_size,
                # short utterances: don't carry context (avoids repetition loops)
                "condition_on_previous_text": False,
                # decode at higher temperatures only if low-temp output looks bad
                "temperature": [0.0, 0.2, 0.4],
                "initial_prompt": self._build_initial_prompt(hint_names),
            }
            if settings.whisper_vad:
                kwargs["vad_filter"] = True
                kwargs["vad_parameters"] = dict(min_silence_duration_ms=500)
            segments, _info = self._whisper.transcribe(wav, **kwargs)
            parts = []
            for seg in segments:
                # skip segments the model itself flags as likely non-speech
                if getattr(seg, "no_speech_prob", 0.0) > 0.6:
                    continue
                text = (seg.text or "").strip()
                if text:
                    parts.append(text)
            transcript = "".join(parts).strip()
        except Exception:
            transcript = ""

        # --- voiceprint -------------------------------------------------
        processed = self._preprocess_wav(wav, source_sr=16000)
        embedding = self._encoder.embed_utterance(processed)
        embedding = np.asarray(embedding, dtype=np.float32)

        return transcript, embedding


engine = VoiceEngine()
