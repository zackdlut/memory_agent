"""Central configuration loaded from environment / .env file.

The project reuses the Ollama endpoint declared via the ANTHROPIC_* variables
(that is what the local toolchain ships with) but talks to Ollama's native
`/api/chat` and `/api/embeddings` endpoints, which are what the server actually
exposes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


def _get(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


@dataclass
class Settings:
    # --- LLM / embeddings ------------------------------------------------
    llm_base_url: str = field(
        default_factory=lambda: (
            _get("LLM_BASE_URL", "ANTHROPIC_BASE_URL", default="http://localhost:11434")
            or "http://localhost:11434"
        ).rstrip("/")
    )
    auth_token: str = field(
        default_factory=lambda: _get("ANTHROPIC_AUTH_TOKEN", "LLM_AUTH_TOKEN", default="") or ""
    )
    chat_model: str = field(
        default_factory=lambda: _get("CHAT_MODEL", "ANTHROPIC_MODEL", default="qwen3.5:9b")
        or "qwen3.5:9b"
    )
    embed_model: str = field(
        default_factory=lambda: _get("EMBED_MODEL", default="nomic-embed-text:latest")
        or "nomic-embed-text:latest"
    )
    embed_dim: int = field(default_factory=lambda: int(_get("EMBED_DIM", default="768") or 768))
    request_timeout: float = field(
        default_factory=lambda: float(_get("LLM_TIMEOUT", default="120") or 120)
    )

    # --- storage ---------------------------------------------------------
    data_dir: Path = field(
        default_factory=lambda: Path(_get("DATA_DIR", default="./data") or "./data")
    )

    # --- server ----------------------------------------------------------
    host: str = field(default_factory=lambda: _get("HOST", default="0.0.0.0") or "0.0.0.0")
    port: int = field(default_factory=lambda: int(_get("PORT", default="8000") or 8000))

    # --- chat assistant --------------------------------------------------
    # the AI assistant's display name; it is never modelled as a person.
    assistant_name: str = field(
        default_factory=lambda: _get("ASSISTANT_NAME", default="三叶虫") or "三叶虫"
    )

    # --- voice chat + voiceprint ----------------------------------------
    # All voice deps are lazy-loaded; text-only mode never imports them.
    voice_enabled: bool = field(
        default_factory=lambda: (_get("VOICE_ENABLED", default="1") or "1") not in ("0", "false", "False")
    )
    whisper_model: str = field(
        default_factory=lambda: _get("WHISPER_MODEL", default="small") or "small"
    )
    whisper_device: str = field(
        default_factory=lambda: _get("WHISPER_DEVICE", default="cpu") or "cpu"
    )
    whisper_compute_type: str = field(
        default_factory=lambda: _get("WHISPER_COMPUTE_TYPE", default="int8") or "int8"
    )
    whisper_language: str = field(
        default_factory=lambda: _get("WHISPER_LANGUAGE", default="zh") or "zh"
    )
    # cosine-similarity thresholds for matching a voiceprint to a known person
    voiceprint_threshold: float = field(
        default_factory=lambda: float(_get("VOICEPRINT_THRESHOLD", default="0.72") or 0.72)
    )
    # at/above this similarity we auto-bind the identity without asking
    voiceprint_strong_threshold: float = field(
        default_factory=lambda: float(
            _get("VOICEPRINT_STRONG_THRESHOLD", default="0.70") or 0.70
        )
    )

    # --- retrieval / evolution tuning -----------------------------------
    episodic_top_k: int = 8
    rerank_keep: int = 6
    # weight bonuses used by the self-evolution module
    emotion_weight_gain: float = 0.5
    repeat_weight_gain: float = 0.3
    task_weight_gain: float = 0.2
    decay_factor: float = 0.98
    episodic_prune_min_weight: float = 0.15
    episodic_recency_half_life_days: float = 30.0
    summary_refresh_cooldown_sec: float = 60.0

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # convenience paths
    @property
    def faiss_index_path(self) -> Path:
        return self.data_dir / "episodic.index"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "memory.db"

    @property
    def graph_path(self) -> Path:
        return self.data_dir / "graph.json"


settings = Settings()
