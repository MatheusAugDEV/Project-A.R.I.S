from __future__ import annotations

import json
import threading
from datetime import datetime

import numpy as np
from sentence_transformers import SentenceTransformer

from src.aris.config.settings import settings
from src.aris.memory.policy import sanitize_recalled_memories, should_retrieve_vector_memory, should_store_vector_memory

_embedding_model = None
_vector_lock = threading.RLock()


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


def salvar_memoria_vetorial(texto: str, resposta: str | None = None) -> None:
    pergunta = " ".join(str(texto or "").split()).strip()
    resposta_limpa = " ".join(str(resposta or "").split()).strip()

    if resposta is not None and not should_store_vector_memory(pergunta, resposta_limpa):
        return

    path = settings.vector_memory_path
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    with _vector_lock:
        dados = _carregar_dados_vetoriais(path)
        texto_memoria = pergunta if resposta is None else f"Usuario: {pergunta} | ARIS: {resposta_limpa}"
        embedding = gerar_embedding(texto_memoria)
        if embedding:
            entrada = {
                "texto": texto_memoria,
                "embedding": embedding,
                "timestamp": datetime.now().isoformat(),
            }
            if resposta is not None:
                entrada.update(
                    {
                        "pergunta": pergunta,
                        "resposta": resposta_limpa,
                        "authority": "low",
                        "kind": "dialogue_pair",
                    }
                )
            dados.append(entrada)

        dados = dados[-300:]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(dados, handle, ensure_ascii=False)


def _similaridade(a, b) -> float:
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def buscar_memoria_vetorial(pergunta: str) -> list[str]:
    if not should_retrieve_vector_memory(pergunta):
        return []

    path = settings.vector_memory_path
    if not path.exists():
        return []

    with _vector_lock:
        dados = _carregar_dados_vetoriais(path)

    emb_pergunta = gerar_embedding(pergunta)
    if not emb_pergunta:
        return []

    scores: list[tuple[float, str]] = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        texto = " ".join(str(item.get("texto", "")).split()).strip()
        if not texto:
            continue
        emb = item.get("embedding", [])
        if len(emb) != len(emb_pergunta):
            continue
        sim = _similaridade(emb_pergunta, emb)
        if sim > 0.62:
            scores.append((sim, texto))

    scores.sort(reverse=True)
    return sanitize_recalled_memories([texto for _, texto in scores], limit=4)


def _carregar_dados_vetoriais(path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            dados = json.load(handle)
    except Exception:
        return []
    return dados if isinstance(dados, list) else []
