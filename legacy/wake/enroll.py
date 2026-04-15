"""
enroll.py — Cadastro de voz do usuário para o wake word do ARIS.
Execute uma vez: python enroll.py
"""

import os
import numpy as np
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from audio_frontend import normalize_audio, resolve_input_device, speech_ratio
from speaker_verify import extract_features
from wake_engine import contem_wake, extrair_contexto_texto

SAVE_DIR  = "data/voice_profile"
N_AMOSTRAS = 8
DURACAO    = 4.0   # segundos por amostra
SR         = 16000


# ── Gravação ─────────────────────────────────────────────────────────

def gravar_amostra(indice: int) -> np.ndarray:
    input(f"\n  Amostra {indice + 1}/{N_AMOSTRAS} — pressione Enter e diga uma saudação com 'ARIS': ")
    print("  ● Gravando...", end="", flush=True)
    audio = sd.rec(
        int(SR * DURACAO),
        samplerate=SR,
        channels=1,
        dtype="float32",
        device=resolve_input_device(),
    )
    sd.wait()
    print(" feito.")
    return audio.flatten()


# ── Principal ────────────────────────────────────────────────────────

def main():
    os.makedirs(SAVE_DIR, exist_ok=True)

    print("╔══════════════════════════════════════╗")
    print("║   ARIS — Cadastro de voz              ║")
    print("╚══════════════════════════════════════╝")
    print(f"\nVamos gravar {N_AMOSTRAS} amostras de você dizendo frases naturais com 'ARIS'.")
    print("Exemplos: 'olá ARIS', 'oi ARIS', 'e aí ARIS', 'boa noite ARIS', 'ARIS'.")
    print("O whisper vai verificar cada amostra.\n")

    print("Carregando modelo de verificação...")
    modelo = WhisperModel("tiny", device="cpu", compute_type="int8")
    print("Pronto.\n")

    amostras_ok   = []
    features_list = []

    i = 0
    tentativas = 0
    while len(amostras_ok) < N_AMOSTRAS and tentativas < N_AMOSTRAS * 2:
        tentativas += 1
        audio = normalize_audio(gravar_amostra(i))

        # verifica com whisper
        segs, _ = modelo.transcribe(
            audio,
            language="pt",
            beam_size=4,
            no_speech_threshold=0.28,
            temperature=0.0,
            vad_filter=True,
            initial_prompt=(
                "Frases comuns: olá ARIS, oi ARIS, ei ARIS, e aí ARIS, fala ARIS, "
                "bom dia ARIS, boa tarde ARIS, boa noite ARIS, ARIS."
            ),
        )
        texto = " ".join(s.text for s in segs).strip().lower()
        print(f"  Whisper ouviu: '{texto}'")

        contexto = extrair_contexto_texto(texto)
        ratio_fala = speech_ratio(audio)

        # aceita apenas amostras com wake claro e fala suficiente
        if contem_wake(texto) and contexto.get("nome_no_inicio_ou_fim") and ratio_fala >= 0.18:
            path = os.path.join(SAVE_DIR, f"sample_{len(amostras_ok)}.wav")
            sf.write(path, audio, SR)
            features_list.append(extract_features(audio))
            amostras_ok.append(path)
            print(f"  ✓ Aceito! ({len(amostras_ok)}/{N_AMOSTRAS}) fala={ratio_fala:.2f}")
            i += 1
        else:
            print(f"  ✗ Rejeitado. wake={contexto.get('tem_nome')} fala={ratio_fala:.2f} — tente novamente mais claramente.")

    if len(amostras_ok) < N_AMOSTRAS:
        print(f"\n⚠ Só {len(amostras_ok)} amostras válidas. Salvando mesmo assim.")

    if not features_list:
        print("\n✗ Nenhuma amostra válida. Cadastro cancelado.")
        return

    # salva features médias e individuais para comparação mais robusta
    mean_feat = np.mean(features_list, axis=0)
    np.savez(
        os.path.join(SAVE_DIR, "voice_profile.npz"),
        mean=mean_feat.astype(np.float32),
        samples=np.array(features_list, dtype=np.float32),
    )
    np.save(os.path.join(SAVE_DIR, "voice_features.npy"), mean_feat)

    print(f"\n✓ Perfil salvo em  {SAVE_DIR}/")
    print("  Agora o ARIS vai reconhecer sua voz com mais precisão.")


if __name__ == "__main__":
    main()
