from datetime import datetime
from groq import Groq
import os

cliente = Groq(api_key=os.environ.get("GROQ_API_KEY"))
historico = []

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

def perguntar_ia(pergunta):
    historico.append({"role": "user", "content": pergunta})
    
    resposta = cliente.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Você é o ARIS, um assistente inteligente. Responda sempre em português, de forma direta e útil."},
            *historico
        ]
    )
    
    conteudo = resposta.choices[0].message.content
    historico.append({"role": "assistant", "content": conteudo})
    return conteudo

import json

def carregar_memoria():
    try:
        with open("data/memory.json", "r") as f:
            return json.load(f)
    except:
        return {}

def salvar_memoria(memoria):
    with open("data/memory.json", "w") as f:
        json.dump(memoria, f, indent=4)

