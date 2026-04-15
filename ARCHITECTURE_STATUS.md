# ARIS Architecture Status

## Official Entry Point

The official ARIS runtime currently starts at `main.py`.

Execution flow:

`main.py` -> `src/aris/config/settings.py` -> `src/aris/app/orchestrator.py`

## Active Base

The active and supported codebase is the `src/aris` package:

- `src/aris/app`: orchestration, UI state, and state machine
- `src/aris/ui`: official GUI (`pygame`)
- `src/aris/voice`: audio capture, STT, and TTS
- `src/aris/actions`: action routing, AI responders, and safe commands
- `src/aris/memory`: local memory and vector memory
- `src/aris/config`: runtime settings and paths

## Legacy / Quarantine

The following files are not part of the official runtime flow and should be treated as legacy or quarantine material for now:

- `aris_daemon.py`
- `wake.py`
- `wake_engine.py`
- `enroll.py`
- `capture_wakeword_dataset.py`
- `speaker_verify.py`
- `wake.py.backup`
- `tts.py.backup`
- `VOICE_STACK_OPTIONS.md`
- `WAKEWORD_TRAINING.md`

These files may still be useful as historical reference or for future recovery work, but they are not part of the current supported runtime path.

## Current Runtime Scope

The official ARIS runtime today is a local/manual flow:

- open the app through `main.py`
- load settings and memory
- open the GUI
- accept manual text input or voice capture on demand
- process through local intents, safe commands, search, or AI
- speak the response with TTS

## Explicit Non-Goals of the Current Runtime

Persistent wake word and background daemon execution are not part of the official runtime today.

`wake.py` and `aris_daemon.py` remain only for compatibility and quarantine purposes.

