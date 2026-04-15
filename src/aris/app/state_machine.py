from __future__ import annotations

from enum import Enum
from threading import RLock


class AppState(str, Enum):
    BOOTING = "BOOTING"
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class AppEvent(str, Enum):
    BOOT_COMPLETED = "BOOT_COMPLETED"
    BOOT_FAILED = "BOOT_FAILED"
    RECOVER_REQUESTED = "RECOVER_REQUESTED"
    VOICE_REQUESTED = "VOICE_REQUESTED"
    MANUAL_TEXT_RECEIVED = "MANUAL_TEXT_RECEIVED"
    STT_TEXT_READY = "STT_TEXT_READY"
    STT_NO_INPUT = "STT_NO_INPUT"
    STT_FAILED = "STT_FAILED"
    PROCESSING_COMPLETED = "PROCESSING_COMPLETED"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    TTS_COMPLETED = "TTS_COMPLETED"
    TTS_FAILED = "TTS_FAILED"
    SHUTDOWN_REQUESTED = "SHUTDOWN_REQUESTED"


class InvalidTransitionError(RuntimeError):
    def __init__(self, state: AppState, event: AppEvent):
        super().__init__(f"Transicao invalida: {state.value} -> {event.value}")
        self.state = state
        self.event = event


_TRANSITIONS: dict[AppState, dict[AppEvent, AppState]] = {
    AppState.BOOTING: {
        AppEvent.BOOT_COMPLETED: AppState.IDLE,
        AppEvent.BOOT_FAILED: AppState.ERROR,
        AppEvent.SHUTDOWN_REQUESTED: AppState.SHUTTING_DOWN,
    },
    AppState.IDLE: {
        AppEvent.VOICE_REQUESTED: AppState.LISTENING,
        AppEvent.MANUAL_TEXT_RECEIVED: AppState.PROCESSING,
        AppEvent.SHUTDOWN_REQUESTED: AppState.SHUTTING_DOWN,
    },
    AppState.LISTENING: {
        AppEvent.STT_TEXT_READY: AppState.PROCESSING,
        AppEvent.STT_NO_INPUT: AppState.IDLE,
        AppEvent.STT_FAILED: AppState.ERROR,
        AppEvent.SHUTDOWN_REQUESTED: AppState.SHUTTING_DOWN,
    },
    AppState.PROCESSING: {
        AppEvent.PROCESSING_COMPLETED: AppState.SPEAKING,
        AppEvent.PROCESSING_FAILED: AppState.ERROR,
        AppEvent.SHUTDOWN_REQUESTED: AppState.SHUTTING_DOWN,
    },
    AppState.SPEAKING: {
        AppEvent.TTS_COMPLETED: AppState.IDLE,
        AppEvent.TTS_FAILED: AppState.ERROR,
        AppEvent.SHUTDOWN_REQUESTED: AppState.SHUTTING_DOWN,
    },
    AppState.ERROR: {
        AppEvent.RECOVER_REQUESTED: AppState.BOOTING,
        AppEvent.SHUTDOWN_REQUESTED: AppState.SHUTTING_DOWN,
    },
    AppState.SHUTTING_DOWN: {},
}


class StateMachine:
    def __init__(self, initial_state: AppState = AppState.BOOTING):
        self._state = initial_state
        self._lock = RLock()

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    def can(self, event: AppEvent) -> bool:
        with self._lock:
            return event in _TRANSITIONS[self._state]

    def transition(self, event: AppEvent) -> AppState:
        with self._lock:
            if event not in _TRANSITIONS[self._state]:
                raise InvalidTransitionError(self._state, event)
            self._state = _TRANSITIONS[self._state][event]
            return self._state
