import sys
import os
import threading
from brain import processar
from gui_orbe import InterfaceARIS  # Nome atualizado aqui

# Garante que o Python encontre os arquivos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Criamos a interface passando a função de processar
    app = InterfaceARIS(processar_callback=processar)
    
    # Mensagem inicial no chat da janela
    app.adicionar_mensagem("ARIS", "Olá Matheus! Sistema unificado e pronto. Como posso ajudar?")
    
    # Inicia a interface (o loop de eventos do CustomTkinter)
    app.mainloop()