from __future__ import annotations

import re

MEMORY_SCHEMA_VERSION = 2
MEMORY_POLICY_NAME = "conservative"

_FACT_SIGNAL_PATTERNS = (
    r"\bmeu nome [eé]\b",
    r"\bme chamo\b",
    r"\beu tenho\s+\d{1,3}\s+anos\b",
    r"\beu moro em\b",
    r"\beu trabalho (?:como|com)\b",
    r"\beu gosto de\b",
    r"\bnasci em\b",
)

_AI_FACT_SIGNAL_PATTERNS = (
    r"\bmeu nome [eé]\b",
    r"\bme chamo\b",
    r"\beu tenho\s+\d{1,3}\s+anos\b",
    r"\beu moro em\b",
    r"\beu trabalho (?:como|com)\b",
    r"\bnasci em\b",
)

_COMMAND_PREFIXES = (
    "abra",
    "abrir",
    "abre",
    "open",
    "fale para",
    "fala para",
    "diga para",
    "mande mensagem para",
    "pesquise",
    "busque",
    "procure",
    "pesquisar",
    "buscar",
)

_SEARCH_HINTS = (
    "youtube",
    "video de",
    "videos de",
    "tutorial de",
    "noticias sobre",
    "ultimas noticias",
)

_TEMPORAL_HINTS = (
    "hoje",
    "agora",
    "amanha",
    "ontem",
    "ultimas",
    "noticias",
    "hora",
    "horas",
    "data",
    "semana",
    "clima",
    "preco",
    "cotacao",
)

_COMPLEX_HINTS = (
    "como",
    "por que",
    "porque",
    "explique",
    "passo a passo",
    "me ajuda",
    "me ensina",
    "qual a melhor",
    "melhor forma",
)

_LOW_SIGNAL_RESPONSE_HINTS = (
    "erro no sistema de ia",
    "nao consegui",
    "nao encontrei",
    "esse comando",
    "catalogo seguro",
    "tudo pronto por aqui",
)


def normalize_memory_shape(memory: dict | None) -> dict:
    base = memory if isinstance(memory, dict) else {}
    facts = base.get("fatos")
    patterns = base.get("padroes")
    meta = base.get("meta")

    base["fatos"] = dict(facts) if isinstance(facts, dict) else {}
    base["padroes"] = _normalize_pattern_entries(patterns)

    normalized_meta = dict(meta) if isinstance(meta, dict) else {}
    normalized_meta["schema_version"] = MEMORY_SCHEMA_VERSION
    normalized_meta["memory_policy"] = MEMORY_POLICY_NAME
    base["meta"] = normalized_meta
    return base


def should_extract_local_facts(text: str) -> bool:
    lowered = _normalize_free_text(text)
    if not lowered or _looks_operational_text(lowered):
        return False
    return any(re.search(pattern, lowered) for pattern in _FACT_SIGNAL_PATTERNS)


def should_extract_facts_with_ai(text: str) -> bool:
    lowered = _normalize_free_text(text)
    if not lowered or _looks_operational_text(lowered):
        return False
    if len(lowered) > 280:
        return False
    return any(re.search(pattern, lowered) for pattern in _AI_FACT_SIGNAL_PATTERNS)


def should_reuse_learned_pattern(question: str) -> bool:
    lowered = _normalize_free_text(question)
    if not lowered:
        return False
    if _looks_operational_text(lowered):
        return False
    if any(hint in lowered for hint in _COMPLEX_HINTS):
        return False
    if any(hint in lowered for hint in _TEMPORAL_HINTS):
        return False
    if len(lowered) > 90 or len(lowered.split()) > 10:
        return False
    return True


def should_store_learned_pattern(question: str, answer: str) -> bool:
    lowered_question = _normalize_free_text(question)
    lowered_answer = _normalize_free_text(answer)
    if not should_reuse_learned_pattern(question):
        return False
    if not lowered_answer:
        return False
    if "\n" in (answer or ""):
        return False
    if len(lowered_answer) > 240:
        return False
    if any(marker in lowered_answer for marker in _LOW_SIGNAL_RESPONSE_HINTS):
        return False
    return True


def should_retrieve_vector_memory(question: str) -> bool:
    lowered = _normalize_free_text(question)
    if not lowered:
        return False
    if _looks_operational_text(lowered):
        return False
    if len(lowered) < 18 or len(lowered.split()) < 4:
        return False
    return True


def should_store_vector_memory(question: str, answer: str) -> bool:
    lowered_answer = _normalize_free_text(answer)
    if not should_retrieve_vector_memory(question):
        return False
    if not lowered_answer or len(lowered_answer) < 24:
        return False
    if len(lowered_answer) > 1200:
        return False
    if any(marker in lowered_answer for marker in _LOW_SIGNAL_RESPONSE_HINTS):
        return False
    return True


def sanitize_recalled_memories(items: list[str], *, limit: int = 4) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for item in items:
        text = " ".join(str(item or "").split()).strip()
        if not text:
            continue
        lowered = text.lower()
        if len(text) > 700:
            continue
        if any(marker in lowered for marker in _LOW_SIGNAL_RESPONSE_HINTS):
            continue
        if text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
        if len(cleaned) >= limit:
            break

    return cleaned


def _normalize_pattern_entries(patterns: object) -> list[dict[str, str]]:
    if not isinstance(patterns, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in patterns:
        if not isinstance(item, dict):
            continue
        entrada = _normalize_free_text(item.get("entrada", ""))
        saida = " ".join(str(item.get("saida", "")).split()).strip()
        if not entrada or not saida:
            continue
        normalized.append(
            {
                "entrada": entrada,
                "saida": saida,
                "authority": str(item.get("authority", "low")),
                "source": str(item.get("source", "pattern")),
                "created_at": str(item.get("created_at", "")),
            }
        )
    return normalized[-100:]


def _looks_operational_text(text: str) -> bool:
    return _starts_with_known_prefix(text) or any(hint in text for hint in _SEARCH_HINTS)


def _starts_with_known_prefix(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in _COMMAND_PREFIXES)


def _normalize_free_text(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered
