from __future__ import annotations

import re

from src.aris.actions.commands.registry import resolve_command
from src.aris.actions.models import ActionDecision, Interpretation, SearchRequest
from src.aris.actions.responders.ai import interpretar as _interpretar_com_ia

_PREFIXOS_BUSCA = re.compile(
    r"^(pesquise|busque|procure|pesquisar|buscar|me fala sobre|me conta sobre"
    r"|informacoes sobre|video de|tutorial de"
    r"|noticias sobre)\s+",
    re.IGNORECASE,
)

_EXPLICIT_WEB_SEARCH = re.compile(
    r"^(pesquise|busque|procure|pesquisar|buscar|me fala sobre|me conta sobre|informacoes sobre)\b",
    re.IGNORECASE,
)
_EXPLICIT_VIDEO_SEARCH = re.compile(
    r"^(video de|videos de|tutorial de|youtube de|procure video de|busque video de)\b",
    re.IGNORECASE,
)
_EXPLICIT_NEWS_SEARCH = re.compile(
    r"^(noticias sobre|noticia sobre|ultimas noticias sobre|novidades sobre)\b",
    re.IGNORECASE,
)
_OPEN_QUESTION_HINT = re.compile(
    r"^(me explica|explique|explica|quero entender|me ensina|como posso|qual a diferenca)\b",
    re.IGNORECASE,
)


def extrair_query(texto: str) -> str:
    return _PREFIXOS_BUSCA.sub("", texto).strip()


def build_search_request(texto: str, search_type: str = "web") -> SearchRequest:
    return SearchRequest(
        query=extrair_query(texto),
        search_type=search_type,
        original_text=texto,
    )


def interpretar(texto: str) -> Interpretation:
    dados = _interpretar_com_ia(texto)
    return Interpretation(
        kind=dados.get("tipo", "conversa"),
        target=dados.get("alvo", "usuario"),
        goal=dados.get("objetivo", "responder"),
    )


def decide_action(texto: str, *, local_intent: str | None = None) -> ActionDecision:
    raw_text = (texto or "").strip()
    command_match = resolve_command(raw_text)
    if command_match is not None:
        if command_match.command_id:
            return ActionDecision(
                kind="command",
                raw_text=raw_text,
                command_match=command_match,
            )
        if command_match.command_like:
            return ActionDecision(
                kind="command_unsupported",
                raw_text=raw_text,
                command_match=command_match,
            )

    lowered = raw_text.lower()

    if local_intent and local_intent not in {"pesquisa_web", "pesquisa_video", "pesquisa_noticias"}:
        return ActionDecision(
            kind="local_intent",
            raw_text=raw_text,
            local_intent=local_intent,
        )

    if _EXPLICIT_VIDEO_SEARCH.search(lowered):
        return ActionDecision(
            kind="search",
            raw_text=raw_text,
            search_request=build_search_request(raw_text, "video"),
        )

    if _EXPLICIT_NEWS_SEARCH.search(lowered):
        return ActionDecision(
            kind="search",
            raw_text=raw_text,
            search_request=build_search_request(raw_text, "noticias"),
        )

    if _EXPLICIT_WEB_SEARCH.search(lowered):
        return ActionDecision(
            kind="search",
            raw_text=raw_text,
            search_request=build_search_request(raw_text, "web"),
        )

    if _OPEN_QUESTION_HINT.search(lowered):
        return ActionDecision(kind="ai_response", raw_text=raw_text)

    if local_intent in {"pesquisa_web", "pesquisa_video", "pesquisa_noticias"}:
        search_type = {
            "pesquisa_web": "web",
            "pesquisa_video": "video",
            "pesquisa_noticias": "noticias",
        }[local_intent]
        return ActionDecision(
            kind="search",
            raw_text=raw_text,
            local_intent=local_intent,
            search_request=build_search_request(raw_text, search_type),
        )

    return ActionDecision(kind="ai_response", raw_text=raw_text)
