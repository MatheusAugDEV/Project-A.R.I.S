"""
Motor de wake word do ARIS.
Decide a ativacao combinando wake dedicated opcional, VAD, texto e locutor.
"""

from __future__ import annotations

import os
import re
import unicodedata
from difflib import SequenceMatcher

import numpy as np

from audio_frontend import normalize_audio, speech_ratio
from speaker_verify import load_voice_profile, profile_similarity

SAMPLE_RATE = 16000
STRONG_SIM_THRESHOLD = 0.68
WEAK_SIM_THRESHOLD = 0.56
MIN_SPEECH_RATIO = 0.24
OPENWAKEWORD_THRESHOLD = 0.35
OPENWAKEWORD_STRICT_THRESHOLD = 0.55

_GREETINGS = {
    "ola",
    "oi",
    "ei",
    "hey",
    "ey",
    "e ai",
    "fala",
    "bom dia",
    "boa tarde",
    "boa noite",
    "boa madrugada",
}

_STRONG_WAKE_PHRASES = {
    "aris",
    "oi aris",
    "ola aris",
    "ei aris",
    "e ai aris",
    "fala aris",
    "bom dia aris",
    "boa tarde aris",
    "boa noite aris",
    "boa madrugada aris",
}

_NAME_VARIANTS = {
    "aris",
    "adis",
    "ades",
    "ariz",
    "eris",
    "ares",
    "arisz",
    "airis",
    "haris",
}

_whisper_model = None
_wake_backend = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        print("[WakeEngine] Carregando modelo tiny...")
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        print("[WakeEngine] Pronto.")
    return _whisper_model


def get_openwakeword_backend():
    global _wake_backend
    if _wake_backend is not None:
        return _wake_backend

    modelo_kw = os.getenv("ARIS_OPENWAKEWORD_MODEL", "").strip()
    if not modelo_kw:
        _wake_backend = False
        return _wake_backend

    try:
        from openwakeword.model import Model

        _wake_backend = Model(
            wakeword_model_paths=[modelo_kw],
            inference_framework="onnx",
            vad_threshold=0.2,
        )
        print(f"[WakeEngine] openWakeWord habilitado com modelo: {modelo_kw}")
    except Exception as e:
        print(f"[WakeEngine] openWakeWord indisponivel: {e}")
        _wake_backend = False
    return _wake_backend


def normalize_text(texto: str) -> str:
    texto = texto.lower().strip()
    texto = "".join(
        ch
        for ch in unicodedata.normalize("NFD", texto)
        if unicodedata.category(ch) != "Mn"
    )
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def tokenizar(texto: str) -> list[str]:
    return re.findall(r"\w+", texto)


def palavra_parece_aris(palavra: str) -> bool:
    if palavra in _NAME_VARIANTS:
        return True
    if not 3 <= len(palavra) <= 6:
        return False
    ratio = SequenceMatcher(None, palavra, "aris").ratio()
    if ratio >= 0.82 and ("r" in palavra or "ri" in palavra):
        return True
    return False


def extrair_contexto_texto(texto: str) -> dict:
    normalizado = normalize_text(texto)
    palavras = tokenizar(normalizado)
    posicoes_nome = [i for i, p in enumerate(palavras) if palavra_parece_aris(p)]
    tem_nome = bool(posicoes_nome)
    saudacao = any(expr in normalizado for expr in _GREETINGS)
    standalone = len(palavras) <= 2 and tem_nome
    greeting_with_name = saudacao and tem_nome
    nome_no_inicio_ou_fim = any(i <= 1 or i >= len(palavras) - 2 for i in posicoes_nome)
    wake_phrase_exact = normalizado in _STRONG_WAKE_PHRASES
    prefixo = " ".join(palavras[:3]).strip()
    prefixo_curto = " ".join(palavras[:2]).strip()
    wake_prefix_match = (
        prefixo in _STRONG_WAKE_PHRASES
        or prefixo_curto in _STRONG_WAKE_PHRASES
        or any(normalizado.startswith(frase + " ") for frase in _STRONG_WAKE_PHRASES)
    )
    repeticoes_wake = 0
    for frase in _STRONG_WAKE_PHRASES:
        repeticoes_wake = max(repeticoes_wake, normalizado.count(frase))
    return {
        "texto": texto.strip(),
        "normalizado": normalizado,
        "palavras": palavras,
        "posicoes_nome": posicoes_nome,
        "tem_nome": tem_nome,
        "saudacao": saudacao,
        "standalone": standalone,
        "greeting_with_name": greeting_with_name,
        "nome_no_inicio_ou_fim": nome_no_inicio_ou_fim,
        "wake_phrase_exact": wake_phrase_exact,
        "wake_prefix_match": wake_prefix_match,
        "repeticoes_wake": repeticoes_wake,
    }


def contem_wake(texto: str) -> bool:
    return extrair_contexto_texto(texto)["tem_nome"]


def padrao_wake_forte(contexto: dict) -> bool:
    palavras = contexto["palavras"]
    if not contexto["tem_nome"]:
        return False
    if contexto.get("wake_phrase_exact"):
        return True
    if contexto.get("wake_prefix_match"):
        return True
    if contexto.get("repeticoes_wake", 0) >= 2:
        return True
    if contexto["standalone"]:
        return True
    if contexto["greeting_with_name"] and len(palavras) <= 5 and contexto["nome_no_inicio_ou_fim"]:
        return True
    if len(palavras) <= 3 and contexto["nome_no_inicio_ou_fim"]:
        return True
    return False


def transcrever_wake(audio: np.ndarray) -> str:
    segs, _ = get_whisper_model().transcribe(
        audio,
        language="pt",
        beam_size=4,
        no_speech_threshold=0.28,
        temperature=0.0,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 180},
        condition_on_previous_text=False,
        initial_prompt=(
            "Frases comuns: olá ARIS, oi ARIS, ei ARIS, e aí ARIS, fala ARIS, "
            "bom dia ARIS, boa tarde ARIS, boa noite ARIS, ARIS."
        ),
    )
    return " ".join(s.text for s in segs).strip()


def openwakeword_score(audio: np.ndarray) -> float | None:
    backend = get_openwakeword_backend()
    if not backend:
        return None

    try:
        pred = backend.predict(normalize_audio(audio))
        if not pred:
            return None
        melhor = 0.0
        for valor in pred.values():
            try:
                melhor = max(melhor, float(valor))
            except Exception:
                continue
        return melhor
    except Exception as e:
        print(f"[WakeEngine] openWakeWord falhou: {e}")
        return None


def pontuar_ativacao(texto: str, sim: float | None) -> dict:
    contexto = extrair_contexto_texto(texto)
    tem_perfil = load_voice_profile() is not None
    wake_forte = padrao_wake_forte(contexto)
    score = 0.0

    if contexto["tem_nome"]:
        score += 2.2
    if contexto["nome_no_inicio_ou_fim"]:
        score += 0.7
    if contexto["saudacao"]:
        score += 0.8
    if contexto["greeting_with_name"]:
        score += 1.0
    if contexto["standalone"]:
        score += 0.7
    if contexto.get("wake_phrase_exact"):
        score += 1.0
    if contexto.get("wake_prefix_match"):
        score += 0.9
    if contexto.get("repeticoes_wake", 0) >= 2:
        score += 0.8
    if wake_forte:
        score += 0.9

    if sim is not None:
        if sim >= STRONG_SIM_THRESHOLD:
            score += 1.4
        elif sim >= WEAK_SIM_THRESHOLD:
            score += 0.6
        else:
            score -= 1.2

    ativar = False
    if contexto["tem_nome"]:
        if tem_perfil and sim is None:
            ativar = False
        elif sim is None:
            ativar = (
                score >= 3.5
                and contexto["nome_no_inicio_ou_fim"]
                and wake_forte
            )
        else:
            ativar = (
                (
                    sim >= STRONG_SIM_THRESHOLD
                    and contexto["nome_no_inicio_ou_fim"]
                    and wake_forte
                )
                or (contexto["greeting_with_name"] and sim >= WEAK_SIM_THRESHOLD)
                or (contexto["standalone"] and sim >= 0.60)
                or (
                    (contexto.get("wake_phrase_exact") or contexto.get("wake_prefix_match"))
                    and contexto["nome_no_inicio_ou_fim"]
                    and score >= 4.2
                )
                or (
                    contexto.get("repeticoes_wake", 0) >= 2
                    and contexto["nome_no_inicio_ou_fim"]
                    and score >= 4.2
                )
            )

    return {
        **contexto,
        "sim": sim,
        "score": score,
        "ativar": ativar,
        "tem_perfil": tem_perfil,
        "wake_forte": wake_forte,
    }


def _passa_regra_estrita(resultado: dict, ow_score: float | None, speech: float) -> bool:
    tem_nome = resultado["tem_nome"]
    if not tem_nome:
        return False

    wake_exato = resultado.get("wake_phrase_exact") or resultado.get("wake_prefix_match")
    repetiu = resultado.get("repeticoes_wake", 0) >= 2
    sim = resultado.get("sim")
    score = resultado.get("score", 0.0)

    if wake_exato and speech >= 0.18 and score >= 4.0:
        return True

    if repetiu and speech >= 0.20 and score >= 4.2:
        return True

    if sim is not None and sim >= STRONG_SIM_THRESHOLD and resultado["wake_forte"] and speech >= 0.18:
        return True

    if (
        ow_score is not None
        and ow_score >= OPENWAKEWORD_STRICT_THRESHOLD
        and resultado["nome_no_inicio_ou_fim"]
        and speech >= 0.18
    ):
        return True

    return False


def analisar_buffer(audio: np.ndarray) -> dict:
    audio = np.asarray(audio, dtype=np.float32)
    rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    audio_proc = normalize_audio(audio)
    speech = speech_ratio(audio_proc)
    ow_score = openwakeword_score(audio_proc)

    if speech < 0.16 and (ow_score is None or ow_score < OPENWAKEWORD_THRESHOLD):
        return {
            "texto": "",
            "normalizado": "",
            "palavras": [],
            "posicoes_nome": [],
            "tem_nome": False,
            "saudacao": False,
            "standalone": False,
            "greeting_with_name": False,
            "nome_no_inicio_ou_fim": False,
            "wake_phrase_exact": False,
            "wake_prefix_match": False,
            "repeticoes_wake": 0,
            "tem_perfil": load_voice_profile() is not None,
            "wake_forte": False,
            "sim": None,
            "score": -1.0,
            "ativar": False,
            "rms": rms,
            "peak": peak,
            "speech_ratio": speech,
            "ow_score": ow_score,
            "should_log": False,
        }

    sim = profile_similarity(audio_proc)
    texto = transcrever_wake(audio_proc)
    resultado = pontuar_ativacao(texto, sim)

    if speech >= MIN_SPEECH_RATIO:
        resultado["score"] += 0.8
    elif speech >= 0.10:
        resultado["score"] += 0.3
    else:
        resultado["score"] -= 0.6

    if ow_score is not None:
        if ow_score >= OPENWAKEWORD_THRESHOLD:
            resultado["score"] += 1.6
        elif ow_score >= 0.20:
            resultado["score"] += 0.5
        else:
            resultado["score"] -= 0.4

    resultado["ativar"] = resultado["ativar"] and _passa_regra_estrita(resultado, ow_score, speech)

    resultado["rms"] = rms
    resultado["peak"] = peak
    resultado["speech_ratio"] = speech
    resultado["ow_score"] = ow_score
    resultado["should_log"] = bool(
        resultado["tem_nome"]
        or resultado["greeting_with_name"]
        or (ow_score is not None and ow_score >= 0.20)
    )
    return resultado
