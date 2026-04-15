from __future__ import annotations

import json
import re
import threading
from datetime import datetime

from src.aris.config.settings import settings
from src.aris.memory.policy import (
    normalize_memory_shape,
    should_extract_local_facts,
    should_reuse_learned_pattern,
    should_store_learned_pattern,
)

_memory_lock = threading.RLock()


def carregar_memoria() -> dict:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = settings.memory_path

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return normalize_memory_shape(json.load(handle))
        except Exception:
            pass

    return normalize_memory_shape({})


def salvar_memoria(memoria: dict) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    memoria = normalize_memory_shape(memoria)
    with open(settings.memory_path, "w", encoding="utf-8") as handle:
        json.dump(memoria, handle, ensure_ascii=False, indent=2)


def aprender_padrao(pergunta: str, resposta: str, memoria: dict) -> dict:
    memoria = normalize_memory_shape(memoria)
    entrada = _normalizar_texto_de_padrao(pergunta)
    saida = " ".join(str(resposta or "").split()).strip()
    if not entrada or not should_store_learned_pattern(entrada, saida):
        return memoria

    for padrao in reversed(memoria["padroes"]):
        if padrao.get("entrada") == entrada and padrao.get("saida") == saida:
            return memoria

    memoria["padroes"].append(
        {
            "entrada": entrada,
            "saida": saida,
            "authority": "low",
            "source": "ai-exact-match",
            "created_at": datetime.now().isoformat(),
        }
    )
    memoria["padroes"] = memoria["padroes"][-100:]
    return memoria


def buscar_padrao(pergunta: str, memoria: dict) -> str | None:
    memoria = normalize_memory_shape(memoria)
    alvo = _normalizar_texto_de_padrao(pergunta)
    if not alvo or not should_reuse_learned_pattern(alvo):
        return None
    for padrao in reversed(memoria.get("padroes", [])):
        entrada = _normalizar_texto_de_padrao(padrao.get("entrada", ""))
        if entrada == alvo:
            return padrao.get("saida")
    return None


def merge_facts(memoria: dict, facts: dict) -> None:
    if not facts:
        return
    with _memory_lock:
        memoria = normalize_memory_shape(memoria)
        memoria.setdefault("fatos", {})
        changed = False
        for raw_key, raw_value in facts.items():
            chave = _sanitize_fact_key(raw_key)
            valor = _sanitize_fact_value(raw_value)
            if not chave or not valor:
                continue
            if memoria["fatos"].get(chave) == valor:
                continue
            memoria["fatos"][chave] = valor
            changed = True
        if changed:
            salvar_memoria(memoria)


def _registrar_fato(memoria: dict, chave: str, valor: str) -> bool:
    valor = _sanitize_fact_value(valor)
    if not valor:
        return False
    memoria.setdefault("fatos", {})
    if memoria["fatos"].get(chave) == valor:
        return False
    memoria["fatos"][chave] = valor
    return True


def _normalizar_texto_de_padrao(texto: str) -> str:
    texto = (texto or "").strip().lower()
    texto = re.sub(r"[?!.,;:]+", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def _sanitize_fact_key(chave: object) -> str:
    texto = str(chave or "").strip().lower()
    texto = re.sub(r"\W+", "_", texto, flags=re.UNICODE).strip("_")
    return texto[:40]


def _sanitize_fact_value(valor: object) -> str:
    if isinstance(valor, (dict, list, tuple, set)):
        return ""
    texto = " ".join(str(valor or "").split()).strip(" .,!?:;\"'")
    if not texto or len(texto) > 160:
        return ""
    return texto


def _extrair_fatos_rapido(texto: str) -> dict[str, str]:
    texto = texto.strip()
    fatos: dict[str, str] = {}
    padroes = [
        ("nome", r"\bmeu nome [eé][\' ]+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{1,40})"),
        ("idade", r"\beu tenho\s+(\d{1,3})\s+anos\b"),
        ("cidade", r"\beu moro em\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{1,40})"),
        ("trabalho", r"\beu trabalho (?:como|com)\s+([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 ,\-]{1,60})"),
        ("gosto", r"\beu gosto de\s+([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 ,\-]{1,60})"),
    ]

    texto_norm = texto.lower()
    for chave, padrao in padroes:
        match = re.search(padrao, texto_norm, re.IGNORECASE)
        if match:
            fatos[chave] = match.group(1).strip()

    return fatos


def update_local_memory(texto: str, memoria: dict) -> bool:
    if not should_extract_local_facts(texto):
        return False

    fatos = _extrair_fatos_rapido(texto)
    if not fatos:
        return False

    changed = False
    with _memory_lock:
        memoria = normalize_memory_shape(memoria)
        memoria.setdefault("fatos", {})
        for chave, valor in fatos.items():
            changed = _registrar_fato(memoria, chave, valor) or changed
        if changed:
            salvar_memoria(memoria)
    return changed
