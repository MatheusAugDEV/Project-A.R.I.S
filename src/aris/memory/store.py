from __future__ import annotations

import json
import re
import threading

from src.aris.config.settings import settings

_history: list[dict[str, str]] = []
_memory_lock = threading.RLock()


def carregar_memoria() -> dict:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = settings.memory_path

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            pass

    return {"fatos": {}, "padroes": []}


def salvar_memoria(memoria: dict) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with open(settings.memory_path, "w", encoding="utf-8") as handle:
        json.dump(memoria, handle, ensure_ascii=False, indent=2)


def aprender_padrao(pergunta: str, resposta: str, memoria: dict) -> dict:
    entrada = _normalizar_texto_de_padrao(pergunta)
    if not entrada:
        return memoria
    memoria.setdefault("padroes", [])
    memoria["padroes"].append({"entrada": entrada, "saida": resposta})
    memoria["padroes"] = memoria["padroes"][-100:]
    return memoria


def buscar_padrao(pergunta: str, memoria: dict) -> str | None:
    alvo = _normalizar_texto_de_padrao(pergunta)
    if not alvo:
        return None
    for padrao in reversed(memoria.get("padroes", [])):
        entrada = _normalizar_texto_de_padrao(padrao.get("entrada", ""))
        if entrada == alvo:
            return padrao.get("saida")
    return None


def append_history(role: str, content: str) -> None:
    with _memory_lock:
        _history.append({"role": role, "content": content})


def get_history_window(limit: int = 16) -> list[dict[str, str]]:
    with _memory_lock:
        return list(_history[-limit:])


def merge_facts(memoria: dict, facts: dict) -> None:
    if not facts:
        return
    with _memory_lock:
        memoria.setdefault("fatos", {})
        memoria["fatos"].update(facts)
        salvar_memoria(memoria)


def _registrar_fato(memoria: dict, chave: str, valor: str) -> bool:
    valor = valor.strip(" .,!?:;\"'")
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


def _extrair_fatos_rapido(texto: str) -> dict[str, str]:
    texto = texto.strip()
    fatos: dict[str, str] = {}
    padroes = [
        ("nome", r"\bmeu nome e[\' ]+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{1,40})"),
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
    fatos = _extrair_fatos_rapido(texto)
    if not fatos:
        return False

    changed = False
    with _memory_lock:
        memoria.setdefault("fatos", {})
        for chave, valor in fatos.items():
            changed = _registrar_fato(memoria, chave, valor) or changed
        if changed:
            salvar_memoria(memoria)
    return changed
