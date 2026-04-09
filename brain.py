from actions import saudacao, hora_atual, data_atual, despedida, perguntar_ia

def processar(comando):
    if any(p in comando for p in ["oi", "olá", "ola", "e aí", "eai", "bom dia", "boa tarde", "boa noite"]):
        return saudacao()

    if any(p in comando for p in ["hora", "horas", "que horas"]):
        return hora_atual()

    if any(p in comando for p in ["data", "dia", "hoje"]):
        return data_atual()

    if any(p in comando for p in ["tchau", "até mais", "ate mais", "encerrar", "bye"]):
        return despedida()

    return perguntar_ia(comando)
