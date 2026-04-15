import os
import sys

print("--- DIAGNÓSTICO DE VOZ ARIS ---")

# 1. Verifica arquivos
files = ["kokoro-v0_19.onnx", "voices.bin"]
for f in files:
    if os.path.exists(f):
        print(f"[OK] Arquivo encontrado: {f}")
    else:
        print(f"[ERRO] Arquivo faltante: {f}. Baixe com wget!")

# 2. Testa Importação
try:
    from kokoro_onnx import Kokoro
    print("[OK] Biblioteca kokoro_onnx carregada.")
except ImportError as e:
    print(f"[ERRO] Falha na importação: {e}")
    sys.exit()

# 3. Testa Áudio
try:
    import sounddevice as sd
    import numpy as np
    print("[OK] Sounddevice carregado. Tentando bipe de teste...")
    # Toca um bipe curto de 0.5s
    fs = 44100
    t = np.linspace(0, 0.5, int(fs * 0.5))
    beep = 0.5 * np.sin(2 * np.pi * 440 * t)
    sd.play(beep, fs)
    sd.wait()
    print("[OK] Áudio do sistema funcional.")
except Exception as e:
    print(f"[ERRO] Placa de som ocupada ou erro: {e}")