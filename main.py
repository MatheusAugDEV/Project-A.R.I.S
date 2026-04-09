from brain import processar

def main():
    print("ARIS iniciado. Digite 'sair' para encerrar.")
    
    while True:
        comando = input("\nVocê: ").strip().lower()
        
        if comando == "sair":
            print("ARIS: Encerrando sistema. Até mais.")
            break
        
        resposta = processar(comando)
        print(f"ARIS: {resposta}")

if __name__ == "__main__":
    main()