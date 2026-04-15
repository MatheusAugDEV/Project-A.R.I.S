from __future__ import annotations

from datetime import datetime

from src.aris.actions.commands.registry import execute_command, resolve_command
from src.aris.actions.models import AIRequest, ActionDecision, CommandResult
from src.aris.actions.responders.ai import perguntar_com_ia
from src.aris.actions.responders.search import pesquisar_com_ia
from src.aris.actions.router import build_search_request, decide_action, interpretar
from src.aris.memory.store import carregar_memoria


def perguntar_ia(pergunta: str, memoria: dict) -> str:
    request = AIRequest(question=pergunta, memory=memoria, original_text=pergunta)
    return perguntar_com_ia(request).text


def pesquisar_ia(pergunta: str, memoria: dict, tipo: str = "web") -> str:
    request = build_search_request(pergunta, tipo)
    return pesquisar_com_ia(request).text


def tentar_executar_comando(texto: str) -> CommandResult | None:
    match = resolve_command(texto)
    if match is None:
        return None
    return execute_command(match)


def resolver_acao_operacional(texto: str, *, local_intent: str | None = None) -> ActionDecision:
    decision = decide_action(texto, local_intent=local_intent)

    if decision.kind == "command" and decision.command_match is not None:
        command_result = execute_command(decision.command_match)
        return ActionDecision(
            kind=decision.kind,
            raw_text=decision.raw_text,
            local_intent=decision.local_intent,
            command_match=decision.command_match,
            search_request=decision.search_request,
            command_result=command_result,
        )

    if decision.kind == "command_unsupported" and decision.command_match is not None:
        target = decision.command_match.target or "esse pedido"
        return ActionDecision(
            kind=decision.kind,
            raw_text=decision.raw_text,
            local_intent=decision.local_intent,
            command_match=decision.command_match,
            search_request=decision.search_request,
            command_result=CommandResult(
                status="not_supported",
                spoken_text=f"Esse comando parece valido, mas '{target}' ainda nao esta no meu catalogo seguro.",
                command_id=None,
            ),
        )

    return decision


def saudacao() -> str:
    hora = datetime.now().hour
    if 5 <= hora < 12:
        return "Bom dia. Sistemas prontos."
    if 12 <= hora < 18:
        return "Boa tarde. Sistemas prontos."
    if 18 <= hora < 23:
        return "Boa noite. Sistemas prontos."
    return "Boa madrugada. Sistemas prontos."


__all__ = [
    "carregar_memoria",
    "interpretar",
    "perguntar_ia",
    "pesquisar_ia",
    "resolver_acao_operacional",
    "saudacao",
    "tentar_executar_comando",
]
