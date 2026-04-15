#!/usr/bin/env python3
"""
Coleta amostras para treinar uma wake word custom do ARIS.

Estrutura gerada:
data/wakeword_dataset/
  positive/
  negative/

Uso:
  .venv/bin/python capture_wakeword_dataset.py --positive 40 --negative 80
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import sounddevice as sd
import soundfile as sf

from audio_frontend import normalize_audio, resolve_input_device
from wake_engine import SAMPLE_RATE

SR = SAMPLE_RATE
POSITIVE_PROMPTS = [
    "ARIS",
    "olá ARIS",
    "oi ARIS",
    "ei ARIS",
    "e aí ARIS",
    "fala ARIS",
    "bom dia ARIS",
    "boa tarde ARIS",
    "boa noite ARIS",
]
NEGATIVE_PROMPTS = [
    "fale uma frase qualquer sem usar o nome do assistente",
    "conte algo em voz alta sem dizer a wake word",
    "simule conversa ambiente normal sem dizer ARIS",
]


def _gravar_clip(duracao: float) -> list[float]:
    audio = sd.rec(
        int(SR * duracao),
        samplerate=SR,
        channels=1,
        dtype="float32",
        device=resolve_input_device(),
    )
    sd.wait()
    return normalize_audio(audio.flatten())


def _capturar(destino: Path, total: int, duracao: float, positivos: bool):
    prompts = POSITIVE_PROMPTS if positivos else NEGATIVE_PROMPTS
    destino.mkdir(parents=True, exist_ok=True)

    for idx in range(total):
        prompt = prompts[idx % len(prompts)]
        rotulo = "positiva" if positivos else "negativa"
        input(f"\nAmostra {idx + 1}/{total} ({rotulo}) — Enter para gravar. Dica: {prompt}\n")
        print("  gravando...")
        audio = _gravar_clip(duracao)
        path = destino / f"{idx:04d}.wav"
        sf.write(path, audio, SR)
        print(f"  salvo em {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--positive", type=int, default=40, help="quantidade de amostras positivas")
    parser.add_argument("--negative", type=int, default=80, help="quantidade de amostras negativas")
    parser.add_argument("--duration", type=float, default=2.2, help="duracao de cada clip em segundos")
    parser.add_argument(
        "--output",
        default="data/wakeword_dataset",
        help="diretorio base do dataset",
    )
    args = parser.parse_args()

    base = Path(args.output)
    positive_dir = base / "positive"
    negative_dir = base / "negative"

    print("ARIS — Coleta de dataset para wake word")
    print(f"Microfone: {resolve_input_device()}")
    print(f"Saida: {base}")

    _capturar(positive_dir, args.positive, args.duration, positivos=True)
    _capturar(negative_dir, args.negative, args.duration, positivos=False)

    print("\nColeta concluida.")
    print(f"Positivas: {positive_dir}")
    print(f"Negativas: {negative_dir}")


if __name__ == "__main__":
    main()
