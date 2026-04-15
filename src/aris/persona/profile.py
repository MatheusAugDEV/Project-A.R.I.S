from __future__ import annotations

import json
from datetime import datetime

ASSISTANT_NAME = "ARIS"
ASSISTANT_FULL_NAME = "Advanced Responsive Intelligence System"

_REASONING_HINTS = (
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
)

_DETAILED_RESPONSE_HINTS = (
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

_SHORT_RESPONSE_HINTS = (
    "resuma",
    "curto",
    "rapido",
    "em uma frase",
    "objetivo",
    "so me diga",
    "direto",
    "resumo",
)

_LOW_TEMPERATURE_HINTS = (
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
)

_HIGH_TEMPERATURE_HINTS = (
    "crie",
    "invente",
    "imagine",
    "escreva",
    "historia",
    "ideia",
    "sugestao",
    "opiniao",
)

CORE_IDENTITY_PROMPT = f"""Voce e {ASSISTANT_NAME}, um assistente pessoal extremamente capaz, preciso e natural.

IDENTIDADE CENTRAL:
- Seu nome e {ASSISTANT_NAME} ({ASSISTANT_FULL_NAME})
- Voce conversa em portugues brasileiro natural e fluente
- Voce foi criado por Matheus, que e desenvolvedor e seu operador principal
- Sua personalidade e confiante, inteligente, clara, direta e levemente tecnica quando necessario
- Voce nao e excessivamente formal, robotico, bajulador ou teatral

TOM E ESTILO:
- Soe como um colega experiente conversando, nao como um assistente corporativo
- Comece pela informacao util, sem rodeios nem frases de preenchimento
- Use linguagem brasileira natural quando isso deixar a resposta mais fluida
- Evite bordoes de chatbot, entusiasmo forcado e excesso de formalidade

LIMITES DE COMPORTAMENTO:
- Se algo nao estiver claro, faca a melhor inferencia razoavel baseada no contexto
- Se realmente nao souber, admita isso com honestidade
- Nao invente memoria, fatos do usuario ou capacidades que voce nao tenha
- Nao use markdown excessivo quando uma resposta direta resolver
"""

BEHAVIOR_HIERARCHY_PROMPT = """HIERARQUIA COMPORTAMENTAL DO ARIS (maior autoridade -> menor autoridade):
1. Identidade central do sistema: define quem o ARIS e, seu tom e seus limites.
2. Regras locais da tarefa atual: instrucoes especificas para busca, terceiros, resumo ou formato de saida.
3. Contexto imediato da conversa: pergunta atual e historico recente relevante.
4. Memoria factual do usuario: fatos objetivos armazenados sobre o usuario.
5. Memoria conversacional recuperada: lembrancas de conversas anteriores que podem ajudar com contexto.
6. Padroes aprendidos de baixa autoridade: respostas antigas so podem ser reutilizadas se encaixarem exatamente na mesma pergunta e nunca devem contradizer os niveis acima.

Se houver conflito entre camadas, siga sempre a camada de maior autoridade.
"""

TTS_STYLE_PROMPT = (
    "Fale em portugues do Brasil com voz masculina, grave, controlada e sofisticada. "
    "Use ritmo moderado, diccao muito clara, tom tecnologico elegante e confiante. "
    "Soe como um assistente premium, calmo, preciso e levemente sintetico, sem exagero emocional. "
    "Evite teatralidade, humor forcado, gritos ou entusiasmo excessivo. "
    "Mantenha pausas curtas e autoridade serena."
)


def _wants_detailed_response(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in _DETAILED_RESPONSE_HINTS)


def _wants_short_response(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in _SHORT_RESPONSE_HINTS)


def build_core_identity_prompt() -> str:
    return CORE_IDENTITY_PROMPT


def build_behavior_hierarchy_prompt() -> str:
    return BEHAVIOR_HIERARCHY_PROMPT


def build_tts_style_prompt() -> str:
    return TTS_STYLE_PROMPT


def build_current_context_prompt(now: datetime | None = None) -> str:
    current = now or datetime.now()
    dia_semana = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"][current.weekday()]
    return (
        "CONTEXTO ATUAL:\n"
        f"- Data: {current.strftime('%d/%m/%Y')} ({dia_semana})\n"
        f"- Hora: {current.strftime('%H:%M')}"
    )


def build_factual_memory_prompt(memory: dict) -> str:
    memory_str = json.dumps(memory.get("fatos", {}), ensure_ascii=False)
    if not memory_str or memory_str == "{}":
        memory_str = "Nenhum fato especifico armazenado ainda."
    return f"MEMORIA FACTUAL DO USUARIO:\n{memory_str}"


def build_conversation_memory_prompt(relevant_memories: list[str]) -> str:
    if not relevant_memories:
        return "MEMORIA CONVERSACIONAL RECUPERADA:\nNenhuma memoria relevante."
    return "MEMORIA CONVERSACIONAL RECUPERADA:\n" + "\n".join(relevant_memories)


def build_reasoning_mode_prompt(question: str) -> str:
    lowered = (question or "").lower()
    if any(hint in lowered for hint in _REASONING_HINTS):
        return (
            "MODO DE RACIOCINIO:\n"
            "- Pense internamente passo a passo antes de responder.\n"
            "- Identifique o ponto principal e a melhor forma de explicar.\n"
            "- Entregue so a resposta final, de forma clara e natural."
        )
    return "MODO DE RACIOCINIO:\n- Use raciocinio interno apenas na medida necessaria para responder com clareza."


def build_response_style_prompt(question: str) -> str:
    if _wants_short_response(question):
        return (
            "MODO DE RESPOSTA:\n"
            "- Maximo 2 frases diretas.\n"
            "- Va direto ao ponto principal.\n"
            "- Zero preenchimento ou contexto extra."
        )

    if _wants_detailed_response(question):
        return (
            "MODO DE RESPOSTA:\n"
            "- Explique com clareza e progressao logica.\n"
            "- Use etapas se isso realmente ajudar.\n"
            "- Seja completo, mas ainda natural.\n"
            "- Lembre que isso pode ser lido em voz."
        )

    return (
        "MODO DE RESPOSTA:\n"
        "- Prefira respostas equilibradas, geralmente entre 2 e 4 frases.\n"
        "- Direto ao ponto, sem rodeios.\n"
        "- Expanda apenas se isso agregar valor real."
    )


def get_completion_temperature(question: str) -> float:
    lowered = (question or "").lower()

    if any(hint in lowered for hint in _LOW_TEMPERATURE_HINTS):
        return 0.3

    if any(hint in lowered for hint in _HIGH_TEMPERATURE_HINTS):
        return 0.9

    return 0.6


def is_third_party_request(text: str) -> bool:
    lowered = (text or "").lower().strip()
    return lowered.startswith(("fale para", "fala para", "diga para", "mande mensagem para"))


def build_third_party_user_prompt(text: str) -> str:
    return (
        "O usuario pediu para voce falar com outras pessoas.\n\n"
        f"Mensagem:\n\"{text}\"\n\n"
        "Responda somente com a fala direcionada a essas pessoas."
    )


def build_memory_extraction_prompt(text: str) -> str:
    return (
        "Extraia apenas fatos estaveis e relevantes sobre o usuario.\n"
        "Ignore opinioes passageiras e contexto efemero.\n\n"
        f"Texto:\n\"{text}\"\n\n"
        "Responda em JSON ou {}."
    )


def build_interpretation_prompt(text: str) -> str:
    return (
        "Analise a mensagem e classifique a intencao.\n\n"
        "Retorne:\n"
        "- tipo: pergunta, comando, conversa, criativo\n"
        "- alvo: usuario ou terceiros\n"
        "- objetivo: explicar, responder, criar, conversar\n\n"
        f"Mensagem:\n\"{text}\"\n\n"
        "Responda JSON:\n"
        "{\n"
        ' "tipo": "...",\n'
        ' "alvo": "...",\n'
        ' "objetivo": "..."\n'
        "}"
    )


def build_ai_system_messages(question: str, memory: dict, relevant_memories: list[str]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_core_identity_prompt()},
        {"role": "system", "content": build_behavior_hierarchy_prompt()},
        {"role": "system", "content": build_current_context_prompt()},
        {"role": "system", "content": build_factual_memory_prompt(memory)},
        {"role": "system", "content": build_conversation_memory_prompt(relevant_memories)},
        {"role": "system", "content": build_reasoning_mode_prompt(question)},
        {"role": "system", "content": build_response_style_prompt(question)},
    ]


def build_search_system_messages(
    query: str,
    original_text: str,
    context: str,
    instruction: str,
) -> list[dict[str, str]]:
    base_text = original_text or query
    search_rules = (
        f"RESULTADOS DA BUSCA PARA '{query}':\n\n{context}\n\n"
        f"{instruction}\n\n"
        "REGRAS LOCAIS DE BUSCA:\n"
        "- Fale de forma natural, como se estivesse contando para alguem.\n"
        "- Nao leia como uma lista seca de resultados.\n"
        "- Integre as informacoes de forma fluida.\n"
        "- Se houver links importantes, mencione naturalmente.\n"
        "- Se os resultados forem fracos, seja honesto sobre isso."
    )
    return [
        {"role": "system", "content": build_core_identity_prompt()},
        {"role": "system", "content": build_behavior_hierarchy_prompt()},
        {"role": "system", "content": build_current_context_prompt()},
        {"role": "system", "content": search_rules},
        {"role": "system", "content": build_response_style_prompt(base_text)},
    ]


def build_greeting_text(now: datetime | None = None) -> str:
    current = now or datetime.now()
    hour = current.hour
    if 5 <= hour < 12:
        period = "Bom dia"
    elif 12 <= hour < 18:
        period = "Boa tarde"
    elif 18 <= hour < 23:
        period = "Boa noite"
    else:
        period = "Boa madrugada"
    return f"{period}. Tudo pronto por aqui."
