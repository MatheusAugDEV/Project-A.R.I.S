from __future__ import annotations

from duckduckgo_search import DDGS

from src.aris.actions.models import ActionResponse, SearchRequest
from src.aris.actions.responders.ai import MODEL, _get_client
from src.aris.persona import build_search_system_messages


def _buscar_web(query: str, n: int = 5):
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=n))


def _buscar_videos(query: str, n: int = 5):
    with DDGS() as ddgs:
        return list(ddgs.videos(query, max_results=n))


def _buscar_noticias(query: str, n: int = 5):
    with DDGS() as ddgs:
        return list(ddgs.news(query, max_results=n))


def pesquisar_com_ia(request: SearchRequest) -> ActionResponse:
    query = request.query

    try:
        if request.search_type == "video":
            resultados = _buscar_videos(query)
            contexto = "\n".join(
                f"- {r.get('title', '')} | {r.get('publisher', '')} | "
                f"{r.get('content', '')[:120]} | URL: {r.get('url', '')}"
                for r in resultados
            )
            instrucao = "Liste os videos encontrados com titulo, canal e link de forma natural."
        elif request.search_type == "noticias":
            resultados = _buscar_noticias(query)
            contexto = "\n".join(
                f"- [{r.get('source', '')}] {r.get('title', '')}: {r.get('body', '')[:200]}"
                for r in resultados
            )
            instrucao = "Resuma as noticias mais relevantes de forma objetiva e natural."
        else:
            resultados = _buscar_web(query)
            contexto = "\n".join(f"- {r.get('title', '')}: {r.get('body', '')[:250]}" for r in resultados)
            instrucao = "Sintetize as informacoes encontradas de forma clara, direta e conversacional."
    except Exception as exc:
        print(f"[Busca falhou] {exc}")
        return ActionResponse(text=f"Nao consegui realizar a busca por '{query}'.", source="search-error")

    if not resultados:
        return ActionResponse(text=f"Nao encontrei resultados para '{query}'.", source="search-empty")

    mensagens = build_search_system_messages(query, request.original_text, contexto, instrucao)
    mensagens.append({"role": "user", "content": request.original_text or query})

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            messages=mensagens,
            temperature=0.5,
            max_tokens=600,
            top_p=0.9,
        )
        return ActionResponse(text=resp.choices[0].message.content.strip(), source=f"search:{request.search_type}")
    except Exception as exc:
        print(f"[IA pesquisa falhou] {exc}")
        return ActionResponse(text="Erro ao processar os resultados da pesquisa.", source="search-ai-error")
