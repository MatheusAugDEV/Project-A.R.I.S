# Wake Word Custom: ARIS

Este projeto ja esta pronto para usar um modelo custom de wake word com `openWakeWord`.

## O que ja foi integrado

- `openwakeword` instalado no `.venv`
- backend opcional no [wake.py](/home/matheus/ARIS/Project_ARIS/wake.py)
- fallback robusto com `WebRTC VAD + perfil de voz + faster-whisper`

Se a variavel `ARIS_OPENWAKEWORD_MODEL` apontar para um modelo `.onnx`, o `wake.py` passa a incluir a predicao neural dedicada no score de ativacao.

## 1. Coletar dataset

Use o coletor local:

```bash
.venv/bin/python capture_wakeword_dataset.py --positive 60 --negative 120
```

Diretorios gerados:

- `data/wakeword_dataset/positive`
- `data/wakeword_dataset/negative`

Sugestao para as amostras positivas:

- `ARIS`
- `olá ARIS`
- `oi ARIS`
- `ei ARIS`
- `e aí ARIS`
- `fala ARIS`
- `bom dia ARIS`
- `boa tarde ARIS`
- `boa noite ARIS`

Sugestao para negativas:

- fala comum sem citar `ARIS`
- audio ambiente
- frases parecidas sem a wake word

## 2. Treinar modelo custom com openWakeWord

O repositorio oficial do `openWakeWord` indica que o caminho recomendado para treinar novos modelos e usar o notebook/Colab oficial de treinamento.

Fonte oficial:

- https://github.com/dscripka/openWakeWord

Pontos relevantes do README oficial:

- o projeto informa que treinar novos modelos e simples via notebook/Colab
- os modelos processam audio de 16 kHz PCM
- e possivel usar modelos custom de wake word no `Model(...)`

Fluxo recomendado:

1. abrir o notebook oficial de treinamento do `openWakeWord`
2. usar como positivos os `.wav` em `data/wakeword_dataset/positive`
3. usar como negativos os `.wav` em `data/wakeword_dataset/negative`
4. treinar um modelo com a frase alvo `ARIS`
5. exportar o resultado final para `.onnx`

## 3. Plugar o modelo no ARIS

Depois de gerar o modelo, defina a variavel:

```bash
export ARIS_OPENWAKEWORD_MODEL=/caminho/para/aris_wakeword.onnx
```

Então inicie o sistema normalmente.

O `wake.py` vai logar:

```text
[Wake] openWakeWord habilitado com modelo: ...
```

## 4. Ajustar microfone se necessario

Se o dispositivo padrao estiver errado:

```bash
export ARIS_INPUT_DEVICE=2
```

ou:

```bash
export ARIS_INPUT_DEVICE=usb
```

O `wake.py` escolhe automaticamente o melhor input, mas esse override ajuda quando o sistema insiste no microfone errado.

## 5. Observacao honesta

Sem um modelo custom para `ARIS`, o ganho maior continua vindo do fallback robusto atual.
Com o modelo `.onnx` dedicado, o ARIS passa a usar uma camada neural especifica para a wake word e tende a ficar bem mais estavel e natural.
