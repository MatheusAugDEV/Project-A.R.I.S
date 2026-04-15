"""
Fachada de compatibilidade para o runtime atual do ARIS.

Mantem a API historica de actions.py enquanto a implementacao real
foi separada por responsabilidade em service/, responders/ e memory/.
"""

from src.aris.actions.service import (
    carregar_memoria,
    interpretar,
    perguntar_ia,
    pesquisar_ia,
    resolver_acao_operacional,
    saudacao,
    tentar_executar_comando,
)

__all__ = [
    "carregar_memoria",
    "interpretar",
    "perguntar_ia",
    "pesquisar_ia",
    "resolver_acao_operacional",
    "saudacao",
    "tentar_executar_comando",
]
