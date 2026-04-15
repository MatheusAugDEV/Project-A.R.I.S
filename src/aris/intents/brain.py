"""
ARIS — Brain / Intent Detection
brain.py
"""

import re
from datetime import datetime


# ─── MAPA DE INTENÇÕES ─────────────────────────────────────


INTENCOES = {
    "hora":              r"horas?|que horas|horário",
    "data":              r"data|dia|hoje|semana",
    "saudacao":          r"olá|oi|e aí|fala|bom dia|boa tarde|boa noite",
    "sistema":           r"cpu|memória|ram|disco|sistema|processador",
    "sair":              r"sair|encerrar|fechar|tchau|até logo|desligar",
    "pesquisa_video":    r"\bvídeo\b|\bvideo\b|\byoutube\b|\btutorial\b|\bassistir\b",
    "pesquisa_noticias": r"\bnotícia|\bnoticia|\bnovidades?\b|\búltimas\b|\bo que aconteceu\b",
    "pesquisa_web":      r"\bpesquise\b|\bbusque\b|\bprocure\b|\bpesquisar\b|\bbuscar\b|me fala sobre|me conta sobre|informações sobre|o que é\s|quem é\s|como funciona",
}


def detectar_intencao(texto: str) -> str | None:
    texto_lower = texto.lower()
    for intencao, padrao in INTENCOES.items():
        if re.search(padrao, texto_lower):
            return intencao
    return None


def executar_intencao(intencao: str, texto: str = "") -> str:
    if intencao == "hora":
        return f"Agora são {datetime.now().strftime('%H:%M')}."

    if intencao == "data":
        dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        now = datetime.now()
        return f"Hoje é {dias[now.weekday()]}, {now.strftime('%d/%m/%Y')}."

    if intencao == "saudacao":
        hora = datetime.now().hour
        if 5 <= hora < 12:
            periodo = "Bom dia"
        elif 12 <= hora < 18:
            periodo = "Boa tarde"
        elif 18 <= hora < 23:
            periodo = "Boa noite"
        else:
            periodo = "Boa madrugada"
        return f"{periodo}. Sistemas prontos. Como posso ajudar?"

    if intencao == "sistema":
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.3)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return (
                f"CPU: {cpu}% | "
                f"RAM: {ram.percent}% ({ram.used // 1024**3}GB/{ram.total // 1024**3}GB) | "
                f"Disco: {disk.percent}%"
            )
        except ImportError:
            return "psutil não instalado. Rode: pip install psutil"

    if intencao == "sair":
        return "Encerrando sistemas. Até logo."

    return None
