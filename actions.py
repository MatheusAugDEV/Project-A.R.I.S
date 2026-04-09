from datetime import datetime
from groq import Groq
import os
import json

cliente = Groq(api_key=os.environ.get("GROQ_API_KEY"))
historico = []

# Contexto base do ARIS
CONTEXT_ARIS = """
Você é o ARIS (Artificial Responsive Intelligence System).
- Propósito: ser um assistente pessoal inteligente, que responde perguntas do usuário,
  guarda informações pessoais, ajuda em tarefas do dia a dia e conversa de forma natural.
- Objetivo: criar uma IA prática, modular e expansível, com histórico de diálogo e 
  capacidade de aprendizado, podendo evoluir para voz, GUI ou automação.
- Criador: Matheus Augusto.
- ARIS deve sempre responder de forma útil, direta e em português, usando informações
  da memória do usuário quando relevante.
"""

def saudacao():
    hora = datetime.now().hour
    if 5 <= hora < 12:
        periodo = "Bom dia"
    elif 12 <= hora < 18:
        periodo = "Boa tarde"
    else:
        periodo = "Boa noite"
    return f"{periodo}! Eu sou o ARIS. Como posso ajudar?"

def hora_atual():
    agora = datetime.now().strftime("%H:%M")
    return f"Agora são {agora}."

def data_atual():
    hoje = datetime.now().strftime("%d/%m/%Y")
    return f"Hoje é {hoje}."

def despedida():
    historico.clear()
    return "Até mais! Sistema em standby."

def perguntar_ia(pergunta, memoria={}):
    contexto_usuario = ""
    if "nome" in memoria:
        contexto_usuario += f"O nome do usuário é {memoria['nome']}. "
    if "fatos" in memoria and memoria["fatos"]:
        contexto_usuario += "Fatos conhecidos sobre ele: " + "; ".join(memoria["fatos"]) + ". "

    mensagens = [
        {"role": "system", "content": CONTEXT_ARIS},
    ]
    
    if contexto_usuario:
        mensagens.append({"role": "system", "content": "Informações adicionais do usuário: " + contexto_usuario})

    historico.append({"role": "user", "content": pergunta})
    mensagens.extend(historico)

    resposta = cliente.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=mensagens
    )

    conteudo = resposta.choices[0].message.content
    historico.append({"role": "assistant", "content": conteudo})
    return conteudo

def carregar_memoria():
    try:
        with open("data/memory.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def salvar_memoria(memoria):
    with open("data/memory.json", "w", encoding="utf-8") as f:
        json.dump(memoria, f, indent=4, ensure_ascii=False)

