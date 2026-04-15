from __future__ import annotations

import json
import os
import threading

from groq import Groq

from src.aris.actions.models import AIRequest, ActionResponse
from src.aris.memory.store import (
    append_history,
    aprender_padrao,
    buscar_padrao,
    get_history_window,
    merge_facts,
    salvar_memoria,
    update_local_memory,
)
from src.aris.memory.vector_store import (
    buscar_memoria_vetorial,
    salvar_memoria_vetorial,
    warmup_embedding_model,
)
from src.aris.persona import (
    build_ai_system_messages,
    build_core_identity_prompt,
    build_interpretation_prompt,
    build_memory_extraction_prompt,
    build_third_party_user_prompt,
    get_completion_temperature,
    is_third_party_request,
)

MODEL = "llama-3.3-70b-versatile"
_client = None


def _get_client():
    global _client
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY ausente.")
    if _client is None:
        _client = Groq(api_key=api_key)
    return _client

CONTEXT_ARIS = build_core_identity_prompt()


def _deve_usar_ia_memoria(texto: str) -> bool:
    gatilhos = ("meu nome", "me chamo", "minha idade", "tenho ", "nasci")
    texto = texto.lower()
    return any(gatilho in texto for gatilho in gatilhos)


def atualizar_memoria_com_ia(texto: str, memoria: dict) -> dict:
    prompt = build_memory_extraction_prompt(texto)

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=150,
        )

        conteudo = resp.choices[0].message.content.strip()
        if conteudo.startswith("{"):
            dados = json.loads(conteudo)
            if isinstance(dados, dict):
                merge_facts(memoria, dados)
    except Exception as exc:
        print("Erro memoria:", exc)

    return memoria


def _atualizar_memoria_assincrona(texto: str, memoria: dict) -> None:
    update_local_memory(texto, memoria)

    if not _deve_usar_ia_memoria(texto):
        return

    def _run():
        try:
            atualizar_memoria_com_ia(texto, memoria)
        except Exception as exc:
            print(f"Erro memoria assincrona: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def interpretar(texto: str) -> dict:
    prompt = build_interpretation_prompt(texto)

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=150,
        )
        conteudo = resp.choices[0].message.content.strip()
        if conteudo.startswith("{"):
            return json.loads(conteudo)
    except Exception as exc:
        print("Erro interpretacao:", exc)

    return {"tipo": "conversa", "alvo": "usuario", "objetivo": "responder"}


def perguntar_com_ia(request: AIRequest) -> ActionResponse:
    pergunta_original = request.original_text or request.question
    memoria = request.memory

    memorias_relevantes: list[str]
    if pergunta_original and is_third_party_request(pergunta_original):
        pergunta_tratada = build_third_party_user_prompt(pergunta_original)
    else:
        pergunta_tratada = request.question

    resposta_padrao = buscar_padrao(pergunta_original, memoria)
    if resposta_padrao:
        return ActionResponse(text=resposta_padrao, source="memory-pattern")

    try:
        memorias_relevantes = buscar_memoria_vetorial(pergunta_original)
    except Exception:
        memorias_relevantes = []
        warmup_embedding_model()

    update_local_memory(pergunta_original, memoria)
    mensagens = build_ai_system_messages(pergunta_original, memoria, memorias_relevantes)
    mensagens += get_history_window(16)
    mensagens.append({"role": "user", "content": pergunta_tratada})

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            messages=mensagens,
            temperature=get_completion_temperature(pergunta_original),
            max_tokens=600,
            top_p=0.9,
        )

        resposta = resp.choices[0].message.content.strip()
        append_history("user", pergunta_original)
        append_history("assistant", resposta)

        threading.Thread(
            target=salvar_memoria_vetorial,
            args=(f"Usuario: {pergunta_original} | ARIS: {resposta}",),
            daemon=True,
        ).start()

        memoria = aprender_padrao(pergunta_original, resposta, memoria)
        salvar_memoria(memoria)
        _atualizar_memoria_assincrona(pergunta_original, memoria)

        return ActionResponse(text=resposta, source="ai")
    except Exception as exc:
        print("Erro IA:", exc)
        return ActionResponse(text="Erro no sistema de IA.", source="ai-error")
