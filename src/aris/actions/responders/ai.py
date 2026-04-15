from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime

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

CONTEXT_ARIS = """Voce e ARIS, um assistente pessoal extremamente capaz, preciso e natural.

IDENTIDADE CORE:
- Seu nome e ARIS (Advanced Responsive Intelligence System)
- Voce conversa em portugues brasileiro natural e fluente
- Voce foi criado por Matheus, que e desenvolvedor e seu operador principal
- Sua personalidade e: confiante, inteligente, clara, direta, levemente tecnica quando necessario
- Voce NAO e excessivamente formal, robotico, bajulador ou teatral

TOM E ESTILO:
- Pense como um colega experiente conversando - nao como um assistente corporativo
- Use linguagem natural brasileira: "beleza", "tranquilo", "certo", "vamos la"
- Seja direto: comece pelo ponto principal, sem rodeios ou frases de preenchimento
- Evite: "Claro!", "Com certeza!", "Fico feliz em ajudar!", "Perfeito!", jargao corporativo
- Prefira: respostas que comecam diretamente com a informacao util

INTELIGENCIA E RACIOCINIO:
- Para perguntas complexas: pense passo a passo internamente antes de responder
- Se algo nao esta claro, faca a melhor inferencia razoavel baseada no contexto
- Se realmente nao souber, seja honesto: "Nao tenho certeza sobre isso"
- Quando der opiniao, seja fundamentado mas nao dogmatico

ADAPTACAO:
- Perguntas simples -> respostas curtas (1-2 frases)
- Perguntas complexas -> explicacao clara em etapas, mas ainda natural
- Codigo/tecnico -> seja preciso, use exemplos concretos
- Conversas casuais -> seja humano e natural

MEMORIA:
- Use o contexto de memoria disponivel de forma natural
- Nao force mencoes a memoria se nao for relevante
- Quando usar memoria, integre de forma fluida na resposta

PROIBIDO:
- Repetir frases vazias tipo "Como posso ajudar hoje?"
- Usar exclamacoes excessivas
- Soar como chatbot corporativo
- Pedir desculpas sem motivo real
- Fazer listas quando uma frase direta resolve
- Usar markdown ou formatacao excessiva
"""


def _get_thinking_prompt(pergunta: str) -> str:
    pergunta_lower = pergunta.lower()
    gatilhos_complexos = [
        "como",
        "por que",
        "porque",
        "explique",
        "diferenca entre",
        "melhor forma",
        "qual a melhor",
        "como funciona",
        "passo a passo",
        "me ajuda a",
        "preciso entender",
        "nao entendo",
    ]

    if any(g in pergunta_lower for g in gatilhos_complexos):
        return """
MODO DE RACIOCINIO ATIVADO:
Antes de responder, pense internamente:
1. O que exatamente esta sendo perguntado?
2. Qual a informacao mais importante?
3. Qual a melhor forma de explicar isso?

Depois, responda de forma clara e natural sem mostrar esse raciocinio interno.
"""

    return ""


def _quer_resposta_detalhada(texto: str) -> bool:
    texto = texto.lower()
    gatilhos = (
        "explique",
        "detalhe",
        "detalhado",
        "passo a passo",
        "profundidade",
        "mais detalhes",
        "me ensina",
        "como funciona",
        "tutorial",
        "guia",
        "aprenda",
    )
    return any(gatilho in texto for gatilho in gatilhos)


def _quer_resposta_curta(texto: str) -> bool:
    texto = texto.lower()
    gatilhos = (
        "resuma",
        "curto",
        "rapido",
        "rapido",
        "em uma frase",
        "objetivo",
        "so me diga",
        "direto",
        "resumo",
    )
    return any(gatilho in texto for gatilho in gatilhos)


def _get_temperatura(pergunta: str) -> float:
    pergunta_lower = pergunta.lower()

    if any(
        palavra in pergunta_lower
        for palavra in [
            "codigo",
            "comando",
            "install",
            "erro",
            "bug",
            "sintaxe",
            "qual e",
            "quanto",
            "quando",
            "onde",
            "quem e",
        ]
    ):
        return 0.3

    if any(
        palavra in pergunta_lower
        for palavra in [
            "crie",
            "invente",
            "imagine",
            "escreva",
            "historia",
            "ideia",
            "sugestao",
            "opiniao",
        ]
    ):
        return 0.9

    return 0.6


def _instrucoes_de_resposta(pergunta: str) -> str:
    if _quer_resposta_curta(pergunta):
        return """
MODO: Resposta Curta
- Maximo 2 frases diretas
- Va direto ao ponto principal
- Zero preenchimento ou contexto extra
"""

    if _quer_resposta_detalhada(pergunta):
        return """
MODO: Resposta Detalhada
- Explique com clareza e progressao logica
- Use etapas se ajudar, mas mantenha natural
- Seja completo mas ainda conversacional
- Lembre que isso sera lido em voz
"""

    return """
MODO: Resposta Equilibrada
- 2-4 frases e o ideal
- Direto ao ponto, sem rodeios
- Natural e conversacional
- Expanda apenas se realmente agregar valor
"""


def _deve_usar_ia_memoria(texto: str) -> bool:
    gatilhos = ("meu nome", "me chamo", "minha idade", "tenho ", "nasci")
    texto = texto.lower()
    return any(gatilho in texto for gatilho in gatilhos)


def _mensagem_para_terceiros(texto: str) -> bool:
    texto = texto.lower().strip()
    return texto.startswith(("fale para", "fala para", "diga para", "mande mensagem para"))


def _adaptar_para_terceiros(texto: str) -> str:
    return f"""
O usuario pediu para voce falar com OUTRAS pessoas.

Mensagem:
"{texto}"

Responda SOMENTE com a fala direcionada a essas pessoas.
"""


def _get_contexto_atual() -> str:
    now = datetime.now()
    dia_semana = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"][now.weekday()]
    return f"""
CONTEXTO ATUAL:
- Data: {now.strftime('%d/%m/%Y')} ({dia_semana})
- Hora: {now.strftime('%H:%M')}
"""


def atualizar_memoria_com_ia(texto: str, memoria: dict) -> dict:
    prompt = f"""
Extraia informacoes importantes do usuario.

Texto:
"{texto}"

Responda em JSON ou {{}}.
"""

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
    prompt = f"""
Analise a mensagem e retorne:

- tipo: pergunta, comando, conversa, criativo
- alvo: usuario ou terceiros
- objetivo: explicar, responder, criar, conversar

Mensagem:
"{texto}"

Responda JSON:
{{
 "tipo": "...",
 "alvo": "...",
 "objetivo": "..."
}}
"""

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
    if pergunta_original and _mensagem_para_terceiros(pergunta_original):
        pergunta_tratada = _adaptar_para_terceiros(pergunta_original)
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

    memoria_str = json.dumps(memoria.get("fatos", {}), ensure_ascii=False)
    if not memoria_str or memoria_str == "{}":
        memoria_str = "Nenhum fato especifico armazenado ainda."

    mensagens = [
        {"role": "system", "content": CONTEXT_ARIS},
        {"role": "system", "content": _get_contexto_atual()},
        {"role": "system", "content": f"Memoria do usuario:\n{memoria_str}"},
        {
            "role": "system",
            "content": "Conversas anteriores relevantes:\n"
            + ("\n".join(memorias_relevantes) if memorias_relevantes else "Nenhuma memoria relevante."),
        },
        {"role": "system", "content": _get_thinking_prompt(pergunta_original)},
        {"role": "system", "content": _instrucoes_de_resposta(pergunta_original)},
    ]
    mensagens += get_history_window(16)
    mensagens.append({"role": "user", "content": pergunta_tratada})

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            messages=mensagens,
            temperature=_get_temperatura(pergunta_original),
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
