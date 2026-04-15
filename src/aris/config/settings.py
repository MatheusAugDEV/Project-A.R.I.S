from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    project_root: Path
    src_root: Path
    aris_root: Path
    data_dir: Path
    models_dir: Path
    env_path: Path
    memory_path: Path
    vector_memory_path: Path
    piper_model_path: Path
    piper_bin: str
    stt_model_size: str
    stt_language: str
    stt_sample_rate: int
    stt_channels: int
    stt_dtype: str
    stt_max_secs: int
    stt_chunk_size: int
    stt_preroll_ms: int
    stt_start_timeout_ms: int
    stt_silence_hold_ms: int
    stt_min_speech_ms: int
    stt_energy_floor: float
    stt_energy_mult: float
    stt_energy_ceiling: float
    stt_peak_trigger_mult: float
    stt_start_trigger_chunks: int
    stt_min_voiced_chunks: int
    stt_min_speech_ratio: float
    tts_backend: str
    tts_google_model: str
    tts_google_voice: str
    tts_google_timeout: float
    tts_google_retries: int


def _build_settings() -> Settings:
    aris_root = Path(__file__).resolve().parent.parent
    src_root = aris_root.parent
    project_root = src_root.parent
    data_dir = project_root / "data"
    models_dir = project_root / "models"
    env_path = project_root / ".env"
    load_dotenv(env_path)

    return Settings(
        project_root=project_root,
        src_root=src_root,
        aris_root=aris_root,
        data_dir=data_dir,
        models_dir=models_dir,
        env_path=env_path,
        memory_path=data_dir / "memory.json",
        vector_memory_path=data_dir / "vector_memory.json",
        piper_model_path=models_dir / "piper" / "pt_BR-faber-medium.onnx",
        piper_bin=os.getenv(
            "ARIS_PIPER_BIN",
            str(project_root / ".venv" / "bin" / "piper"),
        ),
        stt_model_size=os.getenv("ARIS_STT_MODEL_SIZE", "base"),
        stt_language=os.getenv("ARIS_STT_LANGUAGE", "pt"),
        stt_sample_rate=int(os.getenv("ARIS_STT_SAMPLE_RATE", "16000")),
        stt_channels=int(os.getenv("ARIS_STT_CHANNELS", "1")),
        stt_dtype=os.getenv("ARIS_STT_DTYPE", "float32"),
        stt_max_secs=int(os.getenv("ARIS_STT_MAX_SECS", "8")),
        stt_chunk_size=int(os.getenv("ARIS_STT_CHUNK_SIZE", "512")),
        stt_preroll_ms=int(os.getenv("ARIS_STT_PREROLL_MS", "280")),
        stt_start_timeout_ms=int(os.getenv("ARIS_STT_START_TIMEOUT_MS", "3000")),
        stt_silence_hold_ms=int(os.getenv("ARIS_STT_SILENCE_HOLD_MS", "950")),
        stt_min_speech_ms=int(os.getenv("ARIS_STT_MIN_SPEECH_MS", "420")),
        stt_energy_floor=float(os.getenv("ARIS_STT_ENERGY_FLOOR", "0.010")),
        stt_energy_mult=float(os.getenv("ARIS_STT_ENERGY_MULT", "2.4")),
        stt_energy_ceiling=float(os.getenv("ARIS_STT_ENERGY_CEILING", "0.060")),
        stt_peak_trigger_mult=float(os.getenv("ARIS_STT_PEAK_TRIGGER_MULT", "1.85")),
        stt_start_trigger_chunks=int(os.getenv("ARIS_STT_START_TRIGGER_CHUNKS", "2")),
        stt_min_voiced_chunks=int(os.getenv("ARIS_STT_MIN_VOICED_CHUNKS", "4")),
        stt_min_speech_ratio=float(os.getenv("ARIS_STT_MIN_SPEECH_RATIO", "0.18")),
        tts_backend=os.getenv("ARIS_TTS_BACKEND", "piper").strip().lower(),
        tts_google_model=os.getenv(
            "ARIS_GOOGLE_TTS_MODEL",
            "gemini-2.5-flash-preview-tts",
        ),
        tts_google_voice=os.getenv("ARIS_GOOGLE_TTS_VOICE", "Orus"),
        tts_google_timeout=float(os.getenv("ARIS_GOOGLE_TTS_TIMEOUT", "30")),
        tts_google_retries=max(1, int(os.getenv("ARIS_GOOGLE_TTS_RETRIES", "2"))),
    )


settings = _build_settings()
