# ARIS Voice Stack Options

Este documento resume opcoes reais para evoluir o sistema de voz do ARIS com foco em:

- wake word mais confiavel
- menos falsos acionamentos
- melhor captacao em notebook
- menor latencia
- caminho de evolucao para C++/Rust sem reescrever tudo agora

## Pipeline Ideal

Microfone -> VAD -> Wake Word -> Verificacao de Locutor -> Abrir/Focar ARIS -> STT completo -> Comando/IA -> TTS

## Recomendacao Principal

Para o ARIS, o melhor caminho hoje e:

1. manter a aplicacao principal em Python
2. trocar o wake atual baseado em transcricao por um wake dedicado
3. usar VAD melhor antes de qualquer transcricao
4. usar verificacao de locutor com modelo mais forte
5. deixar C++ ou Rust para os modulos de audio em uma segunda fase

## Opcoes por camada

### 1. VAD

#### Opcao atual

- `webrtcvad`

Pontos fortes:

- leve
- simples
- roda bem em CPU

Pontos fracos:

- pode ser agressivo demais
- pior em ruido real e voz distante do que modelos mais novos

#### Opcao recomendada agora

- `Silero VAD`

Motivo:

- costuma ser bem mais robusto para fala real
- lida melhor com ruido e fala fraca
- funciona bem em pipeline local

#### Opcao avancada

- `ten-vad`

Motivo:

- foco em baixa latencia
- mais moderno para pipeline de agente de voz

### 2. Wake Word

#### Opcao atual

- Whisper/faster-whisper tentando inferir o nome "ARIS" pela transcricao

Problema:

- isso nao e wake word de verdade
- transcritor pode alucinar
- ruido e fala aleatoria podem virar "ARIS"

#### Melhor opcao pronta

- `Porcupine` com wake customizado `ARIS`

Motivo:

- foi feito para always-listening
- muito leve
- tem SDK em Python e C
- ideal para notebook e baixa latencia

Tradeoff:

- depende de AccessKey e modelo customizado

#### Melhor opcao open-source

- `openWakeWord` com modelo treinado para `ARIS`

Motivo:

- local
- flexivel
- boa opcao para personalizar sem prender o projeto

Tradeoff:

- exige dataset e treinamento melhor para chegar em nivel premium

#### Opcao mais avancada para migracao futura

- `sherpa-onnx` keyword spotting

Motivo:

- stack forte para speech embarcado
- bom caminho para C++ e mobile

### 3. Verificacao de Locutor

#### Opcao atual

- features MFCC artesanais

Problema:

- e util como filtro inicial
- mas nao e o ideal para alta confiabilidade

#### Opcao recomendada

- `sherpa-onnx` speaker identification

Motivo:

- embeddings de locutor mais fortes
- melhor que heuristica manual
- tem caminho de uso em Python e C++

#### Outra opcao forte

- `pyannote.audio`

Motivo:

- muito bom em tarefas de voz

Tradeoff:

- mais pesado
- pior para notebook simples e always-on

### 4. STT

#### Opcao atual

- `faster-whisper`

Pontos fortes:

- excelente para Python
- muito bom custo/beneficio
- bom para comando completo apos wake

#### Alternativa para foco em C++

- `whisper.cpp`

Motivo:

- C/C++ puro
- muito estavel
- bom para CPU
- bom caminho se quisermos migrar partes criticas para binario nativo

#### Alternativa embarcada mais ampla

- `sherpa-onnx`

Motivo:

- cobre keyword spotting, speaker e ASR
- bom para unificar stack local

### 5. TTS

#### Opcao atual

- Google Gemini TTS com fallback para Piper

Problema atual:

- timeout de rede faz cair no fallback

#### Melhor opcao online

- manter Google TTS quando a rede estiver estavel

#### Melhor opcao offline

- `Piper`

Pontos fortes:

- leve
- local
- rapido

Pontos fracos:

- qualidade da voz depende muito do modelo

#### Opcao premium futura

- treinar ou adaptar voz local melhor para tom estilo Jarvis

## Linguagens

### Python

Melhor para:

- orquestracao
- UI
- integracao de IA
- iteracao rapida

Conclusao:

- deve continuar sendo a linguagem principal do ARIS agora

### C++

Melhor para:

- captura de audio em baixa latencia
- wake word
- ASR local de alto desempenho
- componentes residentemente ativos

Conclusao:

- vale a pena para modulos criticos, mas nao para reescrever tudo ja

### Rust

Melhor para:

- servicos de audio estaveis
- baixa chance de crash
- binarios locais robustos

Conclusao:

- excelente opcao para um daemon de audio futuro
- melhor que migracao total imediata para C++ se o foco for confiabilidade

## Frameworks / stacks que fazem mais sentido

### Stack A: Melhor custo-beneficio agora

- Python
- Silero VAD
- Porcupine ou openWakeWord
- faster-whisper
- Piper / Google TTS

Essa e a recomendacao principal para o ARIS agora.

### Stack B: Mais open-source e local

- Python
- Silero VAD
- openWakeWord treinado para ARIS
- sherpa-onnx speaker identification
- faster-whisper ou sherpa-onnx ASR
- Piper

Boa se a prioridade for independência de servicos externos.

### Stack C: Caminho premium tecnico

- daemon de audio em C++ ou Rust
- VAD dedicado
- wake dedicado
- speaker verification dedicada
- app Python falando com o daemon por socket local

Essa e a arquitetura mais robusta, mas e fase 2.

## O que vale fazer agora

### Fase 1

- substituir wake por engine dedicada
- manter Python na aplicacao principal
- usar VAD melhor
- reforcar speaker verification
- manter STT so depois da ativacao

### Fase 2

- mover audio always-on para daemon nativo
- usar IPC local
- reduzir ainda mais falso acionamento e travamentos

## Decisao recomendada para o ARIS

Se a meta e melhorar MUITO sem explodir a complexidade:

- `Silero VAD`
- `Porcupine` se aceitar servico/modelo customizado
- `openWakeWord` se preferir open-source
- `sherpa-onnx` para speaker verification futura
- `faster-whisper` so para comando completo
- `Piper` local como fallback fixo

## Links uteis

- Porcupine: https://picovoice.ai/docs/porcupine/
- Porcupine Python: https://picovoice.ai/docs/quick-start/porcupine-python/
- Porcupine C: https://picovoice.ai/docs/quick-start/porcupine-c/
- openWakeWord: https://github.com/dscripka/openWakeWord
- Silero VAD: https://github.com/snakers4/silero-vad
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- whisper.cpp: https://github.com/ggml-org/whisper.cpp
- sherpa-onnx speaker identification: https://k2-fsa.github.io/sherpa/onnx/speaker-identification/index.html
