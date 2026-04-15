"""
Camada de audio de baixo nivel para o ARIS.
Responsavel por selecionar microfone, medir fala real e preparar audio por sessao.
"""

from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import dataclass
from math import ceil
from typing import Optional

import numpy as np
import sounddevice as sd
import webrtcvad

try:
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad
except Exception:
    torch = None
    get_speech_timestamps = None
    load_silero_vad = None

from src.aris.config.settings import settings

SAMPLE_RATE = settings.stt_sample_rate
CHANNELS = settings.stt_channels
DTYPE = settings.stt_dtype
CHUNK_SIZE = settings.stt_chunk_size
ENERGY_FLOOR = settings.stt_energy_floor
ENERGY_MULT = settings.stt_energy_mult
ENERGY_CEILING = settings.stt_energy_ceiling

_selected_input_device = None
_noise_floor_rms = None
_vad = webrtcvad.Vad(2)
_silero_model = None
_silero_state = None
_silero_lock = threading.Lock()
_silero_loading = False


@dataclass(frozen=True)
class CaptureConfig:
    sample_rate: int = SAMPLE_RATE
    channels: int = CHANNELS
    dtype: str = DTYPE
    chunk_size: int = CHUNK_SIZE
    max_secs: float = float(settings.stt_max_secs)
    preroll_ms: int = settings.stt_preroll_ms
    start_timeout_ms: int = settings.stt_start_timeout_ms
    silence_hold_ms: int = settings.stt_silence_hold_ms
    min_speech_ms: int = settings.stt_min_speech_ms
    energy_floor: float = ENERGY_FLOOR
    energy_mult: float = ENERGY_MULT
    energy_ceiling: float = ENERGY_CEILING
    peak_trigger_mult: float = settings.stt_peak_trigger_mult
    start_trigger_chunks: int = settings.stt_start_trigger_chunks
    min_voiced_chunks: int = settings.stt_min_voiced_chunks
    min_speech_ratio: float = settings.stt_min_speech_ratio


@dataclass(frozen=True)
class CaptureResult:
    session_id: Optional[int]
    accepted: bool
    reason: str
    audio: np.ndarray
    sample_rate: int
    threshold: float
    rms_mean: float
    rms_peak: float
    speech_ratio: float
    active_secs: float
    duration_secs: float
    speech_started: bool


def resolve_input_device():
    global _selected_input_device
    if _selected_input_device is not None:
        return _selected_input_device

    preferido = os.getenv("ARIS_INPUT_DEVICE", "").strip()
    try:
        devices = sd.query_devices()
        default_input, _ = sd.default.device
    except Exception as e:
        print(f"[Audio] Nao foi possivel consultar dispositivos de audio: {e}")
        _selected_input_device = None
        return None

    candidatos = []
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] <= 0:
            continue
        nome = str(dev["name"])
        nome_lower = nome.lower()
        score = 0
        if idx == default_input:
            score += 100
        if any(chave in nome_lower for chave in ("mic", "micro", "input", "alsa", "pipewire", "pulse", "usb")):
            score += 15
        if any(chave in nome_lower for chave in ("monitor", "output", "speaker", "loopback")):
            score -= 30
        if preferido:
            if preferido.isdigit() and idx == int(preferido):
                score += 1000
            elif preferido.lower() in nome_lower:
                score += 1000
        candidatos.append((score, idx, nome, dev["default_samplerate"]))

    if not candidatos:
        print("[Audio] Nenhum dispositivo de entrada encontrado. Usando padrao do sistema.")
        _selected_input_device = None
        return None

    candidatos.sort(reverse=True)
    _, idx, nome, sr = candidatos[0]
    _selected_input_device = idx
    print(f"[Audio] Microfone selecionado: #{idx} {nome} @ {sr:.0f}Hz")
    return _selected_input_device


def get_silero_model():
    global _silero_model, _silero_state, _silero_loading
    if _silero_state is False:
        return None
    if _silero_model is not None:
        return _silero_model
    if load_silero_vad is None or torch is None:
        _silero_state = False
        return None
    if _silero_loading:
        return None

    def _load():
        global _silero_model, _silero_state, _silero_loading
        try:
            model = load_silero_vad()
            with _silero_lock:
                _silero_model = model
                _silero_state = True
            print("[Audio] Silero VAD carregado.")
        except Exception as e:
            with _silero_lock:
                _silero_state = False
            print(f"[Audio] Silero VAD indisponivel: {e}")
        finally:
            _silero_loading = False

    _silero_loading = True
    threading.Thread(target=_load, daemon=True).start()
    return None


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return audio

    audio = audio - float(np.mean(audio))
    peak = float(np.max(np.abs(audio)))
    if peak > 1e-6:
        audio = audio / peak
        audio = np.clip(audio * 0.92, -1.0, 1.0)
    return audio.astype(np.float32)


def audio_to_pcm16(audio: np.ndarray) -> bytes:
    audio = np.asarray(audio, dtype=np.float32)
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767.0).astype(np.int16).tobytes()


def speech_ratio(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float:
    audio = normalize_audio(audio)
    silero_model = get_silero_model()
    if silero_model is not None and torch is not None and audio.size:
        try:
            tensor = torch.from_numpy(audio.astype(np.float32))
            timestamps = get_speech_timestamps(
                tensor,
                silero_model,
                threshold=0.42,
                sampling_rate=sample_rate,
                min_speech_duration_ms=120,
                min_silence_duration_ms=120,
                speech_pad_ms=40,
            )
            if timestamps:
                voiced = sum(max(0, int(ts["end"]) - int(ts["start"])) for ts in timestamps)
                ratio = voiced / max(len(audio), 1)
                return float(np.clip(ratio, 0.0, 1.0))
            return 0.0
        except Exception as e:
            print(f"[Audio] Silero VAD falhou, usando fallback: {e}")

    frame_len = int(sample_rate * 0.03)
    pcm = audio_to_pcm16(audio)
    bytes_per_frame = frame_len * 2
    if len(pcm) < bytes_per_frame:
        return 0.0

    total = 0
    voiced = 0
    for i in range(0, len(pcm) - bytes_per_frame + 1, bytes_per_frame):
        frame = pcm[i : i + bytes_per_frame]
        total += 1
        try:
            if _vad.is_speech(frame, sample_rate):
                voiced += 1
        except Exception:
            continue

    if total == 0:
        return 0.0
    return voiced / total


def calibrate_input_threshold(
    sample_rate: int = SAMPLE_RATE,
    *,
    energy_floor: float = ENERGY_FLOOR,
    energy_mult: float = ENERGY_MULT,
    energy_ceiling: float = ENERGY_CEILING,
) -> float:
    global _noise_floor_rms
    if _noise_floor_rms is not None:
        return _noise_floor_rms

    try:
        frames = sd.rec(
            int(sample_rate * 0.8),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=resolve_input_device(),
        )
        sd.wait()
        rms = float(np.sqrt(np.mean(frames**2)))
        _noise_floor_rms = float(np.clip(rms * energy_mult, energy_floor, energy_ceiling))
        print(f"[Audio] ruido={rms:.4f} -> threshold_energia={_noise_floor_rms:.4f}")
        return _noise_floor_rms
    except Exception as e:
        print(f"[Audio] Calibracao falhou: {e}")
        print(f"[Audio] threshold_energia={energy_floor:.4f} (fallback)")
        _noise_floor_rms = energy_floor
        return _noise_floor_rms


def emit_level(level_callback, level: float):
    if level_callback is None:
        return
    try:
        level_callback(float(np.clip(level, 0.0, 1.0)))
    except Exception:
        pass


def _chunk_rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(chunk), dtype=np.float32)))


def _chunk_peak(chunk: np.ndarray) -> float:
    return float(np.max(np.abs(chunk))) if chunk.size else 0.0


def _chunk_has_speech(
    chunk: np.ndarray,
    sample_rate: int,
    threshold: float,
    *,
    peak_trigger_mult: float,
) -> bool:
    rms = _chunk_rms(chunk)
    peak = _chunk_peak(chunk)
    if rms >= threshold or peak >= threshold * peak_trigger_mult:
        return True

    pcm = audio_to_pcm16(chunk)
    frame_len = int(sample_rate * 0.03) * 2
    if len(pcm) < frame_len:
        return False

    voiced = 0
    total = 0
    for i in range(0, len(pcm) - frame_len + 1, frame_len):
        frame = pcm[i : i + frame_len]
        total += 1
        try:
            if _vad.is_speech(frame, sample_rate):
                voiced += 1
        except Exception:
            continue
    return total > 0 and voiced / total >= 0.5


def _trim_edge_silence(audio: np.ndarray, threshold: float, sample_rate: int) -> np.ndarray:
    if audio.size == 0:
        return audio

    window = max(1, int(sample_rate * 0.02))
    trim_threshold = max(threshold * 0.55, ENERGY_FLOOR * 0.75)
    start = 0
    end = len(audio)

    while start + window < end:
        if _chunk_rms(audio[start : start + window]) >= trim_threshold:
            break
        start += window

    while end - window > start:
        if _chunk_rms(audio[end - window : end]) >= trim_threshold:
            break
        end -= window

    return audio[start:end] if end > start else np.array([], dtype=np.float32)


def capture_interaction_audio(
    *,
    session_id: Optional[int] = None,
    level_callback=None,
    config: Optional[CaptureConfig] = None,
    activation_label: str = "on_demand:unknown",
    cancel_requested=None,
) -> CaptureResult:
    config = config or CaptureConfig()
    threshold = calibrate_input_threshold(
        config.sample_rate,
        energy_floor=config.energy_floor,
        energy_mult=config.energy_mult,
        energy_ceiling=config.energy_ceiling,
    )
    preroll_chunks = max(1, ceil((config.preroll_ms / 1000) * config.sample_rate / config.chunk_size))
    start_timeout_frames = int((config.start_timeout_ms / 1000) * config.sample_rate)
    silence_hold_frames = int((config.silence_hold_ms / 1000) * config.sample_rate)
    min_active_frames = int((config.min_speech_ms / 1000) * config.sample_rate)
    max_frames = int(config.max_secs * config.sample_rate)

    print(
        f"[Audio] Sessao {session_id} capturando "
        f"(activation={activation_label}, threshold={threshold:.4f}, "
        f"preroll={config.preroll_ms}ms, hold={config.silence_hold_ms}ms)"
    )

    preroll = deque(maxlen=preroll_chunks)
    captured_chunks = []
    total_frames = 0
    active_frames = 0
    silence_frames = 0
    speech_started = False
    voiced_chunks = 0
    speech_start_run = 0
    pending_start_frames = 0
    pending_start_chunks = 0
    rms_values = []
    peak_values = []
    cancelled = False

    with sd.InputStream(
        samplerate=config.sample_rate,
        channels=config.channels,
        dtype=config.dtype,
        device=resolve_input_device(),
        blocksize=config.chunk_size,
    ) as stream:
        while total_frames < max_frames:
            if cancel_requested is not None and cancel_requested():
                cancelled = True
                break

            chunk, _ = stream.read(config.chunk_size)
            chunk = chunk.copy().flatten().astype(np.float32)
            total_frames += len(chunk)

            rms = _chunk_rms(chunk)
            peak = _chunk_peak(chunk)
            rms_values.append(rms)
            peak_values.append(peak)
            emit_level(level_callback, rms / max(threshold * 3.0, 1e-6))

            if cancel_requested is not None and cancel_requested():
                cancelled = True
                break

            chunk_has_speech = _chunk_has_speech(
                chunk,
                config.sample_rate,
                threshold,
                peak_trigger_mult=config.peak_trigger_mult,
            )

            if not speech_started:
                preroll.append(chunk)
                if chunk_has_speech:
                    speech_start_run += 1
                    pending_start_frames += len(chunk)
                    pending_start_chunks += 1
                    if speech_start_run >= max(1, config.start_trigger_chunks):
                        speech_started = True
                        captured_chunks.extend(preroll)
                        active_frames += pending_start_frames
                        voiced_chunks += pending_start_chunks
                        silence_frames = 0
                else:
                    speech_start_run = 0
                    pending_start_frames = 0
                    pending_start_chunks = 0
                if total_frames >= start_timeout_frames:
                    break
                continue

            captured_chunks.append(chunk)
            if chunk_has_speech:
                active_frames += len(chunk)
                voiced_chunks += 1
                silence_frames = 0
            else:
                silence_frames += len(chunk)
                if silence_frames >= silence_hold_frames:
                    break

    emit_level(level_callback, 0.0)

    if cancelled:
        duration_secs = total_frames / max(config.sample_rate, 1)
        return CaptureResult(
            session_id=session_id,
            accepted=False,
            reason="cancelled",
            audio=np.array([], dtype=np.float32),
            sample_rate=config.sample_rate,
            threshold=threshold,
            rms_mean=float(np.mean(rms_values)) if rms_values else 0.0,
            rms_peak=max(peak_values) if peak_values else 0.0,
            speech_ratio=0.0,
            active_secs=active_frames / max(config.sample_rate, 1),
            duration_secs=duration_secs,
            speech_started=speech_started,
        )

    if not captured_chunks:
        duration_secs = total_frames / max(config.sample_rate, 1)
        return CaptureResult(
            session_id=session_id,
            accepted=False,
            reason="no_speech_detected",
            audio=np.array([], dtype=np.float32),
            sample_rate=config.sample_rate,
            threshold=threshold,
            rms_mean=float(np.mean(rms_values)) if rms_values else 0.0,
            rms_peak=max(peak_values) if peak_values else 0.0,
            speech_ratio=0.0,
            active_secs=0.0,
            duration_secs=duration_secs,
            speech_started=False,
        )

    audio = np.concatenate(captured_chunks, axis=0).astype(np.float32)
    audio = _trim_edge_silence(audio, threshold, config.sample_rate)
    audio = normalize_audio(audio)

    duration_secs = len(audio) / max(config.sample_rate, 1)
    active_secs = active_frames / max(config.sample_rate, 1)
    ratio = speech_ratio(audio, sample_rate=config.sample_rate)
    rms_mean = float(np.mean(rms_values)) if rms_values else 0.0
    rms_peak = max(peak_values) if peak_values else 0.0

    if audio.size == 0:
        reason = "trimmed_to_empty"
        accepted = False
    elif active_frames < min_active_frames:
        reason = "speech_too_short"
        accepted = False
    elif voiced_chunks < max(1, config.min_voiced_chunks):
        reason = "too_few_voiced_chunks"
        accepted = False
    elif ratio < config.min_speech_ratio:
        reason = "low_speech_ratio"
        accepted = False
    else:
        reason = "ok"
        accepted = True

    print(
        f"[Audio] Sessao {session_id} encerrada "
        f"(activation={activation_label}, accepted={accepted}, reason={reason}, "
        f"active_secs={active_secs:.2f}, ratio={ratio:.2f})"
    )

    return CaptureResult(
        session_id=session_id,
        accepted=accepted,
        reason=reason,
        audio=audio if accepted else np.array([], dtype=np.float32),
        sample_rate=config.sample_rate,
        threshold=threshold,
        rms_mean=rms_mean,
        rms_peak=rms_peak,
        speech_ratio=ratio,
        active_secs=active_secs,
        duration_secs=duration_secs,
        speech_started=speech_started,
    )
