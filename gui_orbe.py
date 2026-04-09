import customtkinter as ctk
import math
import random
import threading  # Importado aqui para evitar lentidão depois

class InterfaceARIS(ctk.CTk):
    def __init__(self, processar_callback):
        super().__init__()

        self.title("A.R.I.S - Intelligence System")
        self.geometry("500x700")
        self.configure(fg_color="#0b0d11")
        
        # Guardamos a função de processar que vem do brain
        self.processar_callback = processar_callback

        # Canvas do Orbe
        self.canvas = ctk.CTkCanvas(self, width=400, height=200, bg="#0b0d11", highlightthickness=0)
        self.canvas.pack(pady=10)
        
        self.centro_x, self.centro_y = 200, 100
        self.raio_base = 50
        self.angulo = 0
        self.estado = "standby"

        # Camadas visuais do Orbe
        self.glow_outer = self.canvas.create_oval(0,0,0,0, fill="#002222", outline="", width=0)
        self.glow_inner = self.canvas.create_oval(0,0,0,0, fill="#00FFFF", outline="", width=0)
        self.core = self.canvas.create_oval(0,0,0,0, fill="#E0FFFF", outline="", width=0)

        # Display do Chat
        self.chat_display = ctk.CTkTextbox(self, width=440, height=350, fg_color="#161b22", corner_radius=15, border_width=1, border_color="#30363d")
        self.chat_display.pack(pady=10, padx=20)
        self.chat_display.configure(state="disabled")

        # Entrada de Texto
        self.entry = ctk.CTkEntry(self, width=440, height=50, placeholder_text="Fale com o ARIS...", corner_radius=25, fg_color="#161b22", border_color="#30363d")
        self.entry.pack(pady=20)
        self.entry.bind("<Return>", self.enviar)

        self.animar()

    def adicionar_mensagem(self, quem, texto):
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", f"\n{quem.upper()}: {texto}\n")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def enviar(self, event=None):
        texto = self.entry.get()
        if texto:
            self.entry.delete(0, 'end')
            self.adicionar_mensagem("Você", texto)
            # Rodar em thread para não travar a animação do orbe
            threading.Thread(target=self.executar_brain, args=(texto,), daemon=True).start()

    def executar_brain(self, texto):
        self.set_estado("processando")
        resposta = self.processar_callback(texto)
        self.set_estado("falando")
        self.adicionar_mensagem("ARIS", resposta)
        self.after(2000, lambda: self.set_estado("standby"))

    def set_estado(self, novo_estado):
        self.estado = novo_estado
        cores = {
            "standby": ("#E0FFFF", "#00FFFF", "#002222"),
            "processando": ("#FFE0FF", "#FF00FF", "#330033"),
            "falando": ("#FFFFE0", "#FFFF00", "#333300")
        }
        if novo_estado in cores:
            c, gi, go = cores[novo_estado]
            self.canvas.itemconfig(self.core, fill=c)
            self.canvas.itemconfig(self.glow_inner, fill=gi)
            self.canvas.itemconfig(self.glow_outer, fill=go)

    def animar(self):
        self.angulo += 0.05
        raio = self.raio_base
        if self.estado == "falando": 
            raio *= (1 + 0.15 * abs(math.sin(self.angulo * 2)))
        elif self.estado == "processando": 
            raio += random.randint(-3, 3)
        else: 
            raio *= (1 + 0.03 * math.sin(self.angulo))

        def d(obj, r): 
            self.canvas.coords(obj, self.centro_x-r, self.centro_y-r, self.centro_x+r, self.centro_y+r)
        
        d(self.glow_outer, raio * 1.4)
        d(self.glow_inner, raio * 1.1)
        d(self.core, raio * 0.8)
        self.after(16, self.animar)