# ARIS Voice Activation Architecture

## Official Runtime Today

The official ARIS runtime is still manual/local:

- `main.py` starts the runtime
- `src/aris/app/orchestrator.py` owns interaction flow and FSM transitions
- GUI can trigger text input or on-demand voice capture
- STT runs only for explicit on-demand sessions

Persistent wake word and daemon-style background listening are **not** part of the supported runtime today.

## Official Activation Modes

### 1. Manual Text

- current status: active
- owner: orchestrator
- starts listening: no
- valid state: `IDLE`
- entry path: GUI text input

### 2. On-Demand Voice

- current status: active
- owner: orchestrator
- starts listening: yes
- valid state: `IDLE`
- entry path today: GUI callback / hotkey-triggered request
- runtime flow:
  - activation request
  - FSM `IDLE -> LISTENING`
  - audio frontend capture
  - STT
  - FSM `LISTENING -> PROCESSING`

### 3. Wake Word

- current status: future / optional
- owner: future wake subsystem
- starts listening: yes
- valid state: `IDLE`
- not implemented as official runtime behavior yet
- any historical wake tooling remains only as quarantine/reference

### 4. Interrupt / Shutdown

- current status: active as runtime control, not as final UX
- owner: orchestrator
- purpose: terminate active flow or shut down runtime safely
- valid states: booting, idle, listening, processing, speaking, error

## Contracts Between Modules

### GUI

- may request on-demand voice activation
- does not own capture logic
- does not own wake word
- does not bypass FSM

### Orchestrator

- owns activation policy and approval/rejection
- owns session lifecycle
- owns FSM transitions
- chooses when STT can start

### Audio Frontend

- captures audio only for an approved session
- does not decide if a session should exist
- does not know about wake word policy

### STT

- consumes approved session capture
- returns transcript or empty result
- does not decide whether activation is allowed

### Future Wake Subsystem

- if implemented later, should only request activation
- must not own the main runtime FSM
- must remain optional and isolated from the manual runtime path
