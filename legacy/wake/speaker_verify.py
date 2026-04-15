"""
Verificacao de locutor para o ARIS.
Mantem o perfil de voz e calcula similaridade com novas amostras.
"""

from __future__ import annotations

import os

import numpy as np

VOICE_PROFILE_DIR = "data/voice_profile"
VOICE_PROFILE_NPZ = os.path.join(VOICE_PROFILE_DIR, "voice_profile.npz")
VOICE_PROFILE_NPY = os.path.join(VOICE_PROFILE_DIR, "voice_features.npy")

_voice_profile = None


def load_voice_profile():
    global _voice_profile
    if _voice_profile is not None:
        return _voice_profile

    if os.path.exists(VOICE_PROFILE_NPZ):
        dados = np.load(VOICE_PROFILE_NPZ)
        mean = dados["mean"].astype(np.float32)
        samples = dados["samples"].astype(np.float32)
        std = np.std(samples, axis=0).astype(np.float32)
        std = np.maximum(std, 1e-3)
        _voice_profile = {"mean": mean, "samples": samples, "std": std}
        print(f"[Speaker] Perfil de voz carregado ({VOICE_PROFILE_NPZ})")
        return _voice_profile

    if os.path.exists(VOICE_PROFILE_NPY):
        mean = np.load(VOICE_PROFILE_NPY).astype(np.float32)
        _voice_profile = {
            "mean": mean,
            "samples": np.array([mean], dtype=np.float32),
            "std": np.ones_like(mean, dtype=np.float32),
        }
        print(f"[Speaker] Perfil legado carregado ({VOICE_PROFILE_NPY})")
        return _voice_profile

    _voice_profile = None
    print("[Speaker] Sem perfil de voz — funcionando sem verificacao de locutor.")
    return _voice_profile


def extract_features(audio: np.ndarray, sr: int = 16000, n_mfcc: int = 20) -> np.ndarray:
    from scipy.fftpack import dct

    if len(audio) == 0:
        return np.zeros(n_mfcc, dtype=np.float32)

    n_fft, hop = 512, 256
    frames = np.array(
        [
            audio[i : i + n_fft] * np.hanning(n_fft)
            for i in range(0, len(audio) - n_fft, hop)
            if i + n_fft <= len(audio)
        ]
    )
    if len(frames) == 0:
        return np.zeros(n_mfcc, dtype=np.float32)

    power = (np.abs(np.fft.rfft(frames)) ** 2) / n_fft
    n_mels = 40
    low_hz, high_hz = 80.0, min(8000.0, sr / 2)
    mel_pts = np.linspace(
        2595 * np.log10(1 + low_hz / 700),
        2595 * np.log10(1 + high_hz / 700),
        n_mels + 2,
    )
    hz_pts = 700 * (10 ** (mel_pts / 2595) - 1)
    bins = np.floor((n_fft + 1) * hz_pts / sr).astype(int)
    fbank = np.zeros((n_mels, n_fft // 2 + 1))

    for m in range(1, n_mels + 1):
        for k in range(bins[m - 1], bins[m]):
            fbank[m - 1, k] = (k - bins[m - 1]) / max(bins[m] - bins[m - 1], 1)
        for k in range(bins[m], bins[m + 1]):
            fbank[m - 1, k] = (bins[m + 1] - k) / max(bins[m + 1] - bins[m], 1)

    log_mel = np.log(np.maximum(np.dot(power, fbank.T), 1e-10))
    mfcc = dct(log_mel, type=2, axis=1, norm="ortho")[:, :n_mfcc]
    return np.mean(mfcc, axis=0).astype(np.float32)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def profile_similarity(audio: np.ndarray) -> float | None:
    profile = load_voice_profile()
    if profile is None:
        return None

    feats = extract_features(audio)
    std = profile.get("std")
    if std is not None:
        feats_cmp = (feats - profile["mean"]) / std
        mean_cmp = np.zeros_like(feats_cmp)
        sample_cmps = [(sample - profile["mean"]) / std for sample in profile["samples"]]
    else:
        feats_cmp = feats
        mean_cmp = profile["mean"]
        sample_cmps = list(profile["samples"])

    sims = [similarity(feats_cmp, mean_cmp)]
    for sample in sample_cmps:
        sims.append(similarity(feats_cmp, sample))

    sims.sort(reverse=True)
    top_k = sims[: min(3, len(sims))]
    return float(np.mean(top_k))
