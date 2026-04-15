from __future__ import annotations

import json
import threading
from datetime import datetime

import numpy as np
from sentence_transformers import SentenceTransformer

from src.aris.config.settings import settings

_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        print("[ARIS] Carregando modelo de embedding...")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def warmup_embedding_model() -> None:
    if _embedding_model is not None:
        return

    def _run():
        try:
            _get_embedding_model()
        except Exception as exc:
            print(f"[ARIS] Falha ao aquecer embedding: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def gerar_embedding(texto: str):
    try:
        return _get_embedding_model().encode(texto).tolist()
    except Exception:
        return None


def salvar_memoria_vetorial(texto: str) -> None:
    path = settings.vector_memory_path
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    if path.exists():
        with open(path, "r", encoding="utf-8") as handle:
            dados = json.load(handle)
    else:
        dados = []

    embedding = gerar_embedding(texto)
    if embedding:
        dados.append(
            {
                "texto": texto,
                "embedding": embedding,
                "timestamp": datetime.now().isoformat(),
            }
        )

    dados = dados[-300:]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(dados, handle, ensure_ascii=False)


def _similaridade(a, b) -> float:
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def buscar_memoria_vetorial(pergunta: str) -> list[str]:
    path = settings.vector_memory_path
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as handle:
        dados = json.load(handle)

    emb_pergunta = gerar_embedding(pergunta)
    if not emb_pergunta:
        return []

    scores: list[tuple[float, str]] = []
    for item in dados:
        emb = item.get("embedding", [])
        if len(emb) != len(emb_pergunta):
            continue
        sim = _similaridade(emb_pergunta, emb)
        if sim > 0.55:
            scores.append((sim, item["texto"]))

    scores.sort(reverse=True)
    return [texto for _, texto in scores[:7]]
