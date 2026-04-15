import threading
import numpy as np
from faster_whisper import WhisperModel
from .audio_frontend import (
    CaptureResult,
    calibrate_input_threshold,
    capture_interaction_audio,
    normalize_audio,
)
from src.aris.config.settings import settings

MODEL_SIZE   = settings.stt_model_size
LANGUAGE     = settings.stt_language
SAMPLE_RATE  = settings.stt_sample_rate

_model     = None
_warmup_started = False


def _get_model():
    global _model
    if _model is None:
        print("[STT] Carregando modelo Whisper...")
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        print("[STT] Modelo pronto.")
    return _model


def _texto_parece_comando(texto: str) -> bool:
    texto = texto.strip()
    if not texto:
        return False

    texto_lower = texto.lower()
    palavras = [p for p in texto_lower.replace(",", " ").replace(".", " ").split() if p]
    if len(palavras) == 1 and len(palavras[0]) <= 2:
        return False
    if len(texto_lower) < 3:
        return False

    ruido_comum = {
        "aham",
        "hum",
        "uh",
        "hã",
        "ahn",
        "mm",
    }
    if len(palavras) <= 2 and all(p in ruido_comum for p in palavras):
        return False

    return True


def transcrever(audio: np.ndarray) -> str:
    if audio.size == 0:
        return ""

    model = _get_model()
    audio = normalize_audio(np.asarray(audio, dtype=np.float32))
    segments, _ = model.transcribe(
        audio,
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,               # Silero VAD — remove não-fala
        vad_parameters={"min_silence_duration_ms": 400},
        condition_on_previous_text=False,
        no_speech_threshold=0.35,
    )
    texto = " ".join(s.text for s in segments).strip()
    print(f"[STT] Transcrito: '{texto}'")
    if not _texto_parece_comando(texto):
        print("[STT] Texto descartado por baixa confianca.")
        return ""
    return texto


def ouvir_com_resultado(
    session_id=None,
    level_callback=None,
    activation_label: str = "on_demand:unknown",
    cancel_requested=None,
) -> tuple[str, CaptureResult]:
    capture = capture_interaction_audio(
        session_id=session_id,
        level_callback=level_callback,
        activation_label=activation_label,
        cancel_requested=cancel_requested,
    )
    if not capture.accepted:
        print(
            f"[STT] Sessao {session_id} descartada no front-end "
            f"(activation={activation_label}, reason={capture.reason}, "
            f"active_secs={capture.active_secs:.2f}, ratio={capture.speech_ratio:.2f})"
        )
        return "", capture

    return transcrever(capture.audio), capture


def ouvir(
    level_callback=None,
    session_id=None,
    activation_label: str = "on_demand:unknown",
    cancel_requested=None,
) -> str:
    texto, _ = ouvir_com_resultado(
        session_id=session_id,
        level_callback=level_callback,
        activation_label=activation_label,
        cancel_requested=cancel_requested,
    )
    return texto


def aquecer():
    global _warmup_started
    if _warmup_started:
        return
    _warmup_started = True

    def _run():
        try:
            calibrate_input_threshold()
        except Exception as e:
            print(f"[STT] Warmup de threshold falhou: {e}")
        try:
            _get_model()
        except Exception as e:
            print(f"[STT] Warmup de modelo falhou: {e}")

    threading.Thread(target=_run, daemon=True).start()


def ouvir_async(
    callback,
    level_callback=None,
    activation_label: str = "on_demand:unknown",
    cancel_requested=None,
):
    def _run():
        texto = ouvir(
            level_callback=level_callback,
            activation_label=activation_label,
            cancel_requested=cancel_requested,
        )
        if texto:
            callback(texto)
    threading.Thread(target=_run, daemon=True).start()
