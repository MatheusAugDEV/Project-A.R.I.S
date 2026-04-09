
from actions import (
    saudacao, hora_atual, data_atual, despedida,
    perguntar_ia, carregar_memoria, salvar_memoria
)

memoria = carregar_memoria()

def processar(comando):
    comando = comando.lower()

    # 👇 MEMÓRIA (NOVO)
    if "meu nome é" in comando:
        nome = comando.replace("meu nome é", "").strip()
        memoria["nome"] = nome
        salvar_memoria(memoria)
        return f"Entendi. Vou lembrar que seu nome é {nome}."

    if "qual meu nome" in comando:
        if "nome" in memoria:
            return f"Seu nome é {memoria['nome']}."
        else:
            return "Você ainda não me disse seu nome."

    # 👇 COMANDOS EXISTENTES
    if any(p in comando for p in ["oi", "olá", "ola", "e aí", "eai", "bom dia", "boa tarde", "boa noite"]):
        return saudacao()

    if any(p in comando for p in ["hora", "horas", "que horas"]):
        return hora_atual()

    if any(p in comando for p in ["data", "dia", "hoje"]):
        return data_atual()

    if any(p in comando for p in ["tchau", "até mais", "ate mais", "encerrar", "bye"]):
        return despedida()

    return perguntar_ia(comando)
