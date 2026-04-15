from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.aris.app.state_machine import AppEvent, AppState


class VoiceActivationMode(str, Enum):
    MANUAL_TEXT = "manual_text"
    ON_DEMAND = "on_demand"
    WAKEWORD = "wakeword"
    INTERRUPT = "interrupt"


class VoiceActivationSource(str, Enum):
    GUI_TEXT = "gui_text"
    HOTKEY_F8 = "hotkey_f8"
    GUI_BUTTON = "gui_button"
    WAKEWORD_ENGINE = "wakeword_engine"
    SHUTDOWN = "shutdown"
    RECOVERY = "recovery"


class VoiceActivationAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    FUTURE = "future"


class VoiceActivationRejection(str, Enum):
    NONE = "none"
    INVALID_STATE = "invalid_state"
    RUNTIME_NOT_READY = "runtime_not_ready"
    INTERACTION_ACTIVE = "interaction_active"
    RECOVERY_IN_PROGRESS = "recovery_in_progress"
    MODE_NOT_IMPLEMENTED = "mode_not_implemented"


@dataclass(frozen=True)
class VoiceActivationProfile:
    mode: VoiceActivationMode
    availability: VoiceActivationAvailability
    starts_listening: bool
    optional_subsystem: bool
    allowed_states: tuple[AppState, ...]
    requires_runtime_ready: bool
    requires_no_active_interaction: bool
    entry_event: AppEvent | None
    termination_events: tuple[AppEvent, ...]
    owner: str
    notes: str


@dataclass(frozen=True)
class VoiceActivationRequest:
    mode: VoiceActivationMode
    source: VoiceActivationSource

    @property
    def activation_label(self) -> str:
        return f"{self.mode.value}:{self.source.value}"


@dataclass(frozen=True)
class VoiceActivationDecision:
    request: VoiceActivationRequest
    accepted: bool
    rejection: VoiceActivationRejection
    profile: VoiceActivationProfile
    message: str


OFFICIAL_VOICE_ACTIVATION_PROFILES: dict[VoiceActivationMode, VoiceActivationProfile] = {
    VoiceActivationMode.MANUAL_TEXT: VoiceActivationProfile(
        mode=VoiceActivationMode.MANUAL_TEXT,
        availability=VoiceActivationAvailability.AVAILABLE,
        starts_listening=False,
        optional_subsystem=False,
        allowed_states=(AppState.IDLE,),
        requires_runtime_ready=True,
        requires_no_active_interaction=True,
        entry_event=AppEvent.MANUAL_TEXT_RECEIVED,
        termination_events=(AppEvent.PROCESSING_COMPLETED, AppEvent.PROCESSING_FAILED, AppEvent.SHUTDOWN_REQUESTED),
        owner="orchestrator",
        notes="Fluxo oficial atual para texto manual via GUI.",
    ),
    VoiceActivationMode.ON_DEMAND: VoiceActivationProfile(
        mode=VoiceActivationMode.ON_DEMAND,
        availability=VoiceActivationAvailability.AVAILABLE,
        starts_listening=True,
        optional_subsystem=False,
        allowed_states=(AppState.IDLE,),
        requires_runtime_ready=True,
        requires_no_active_interaction=True,
        entry_event=AppEvent.VOICE_REQUESTED,
        termination_events=(
            AppEvent.STT_TEXT_READY,
            AppEvent.STT_NO_INPUT,
            AppEvent.STT_FAILED,
            AppEvent.SHUTDOWN_REQUESTED,
        ),
        owner="orchestrator",
        notes="Escuta sob demanda do runtime oficial atual. GUI/hotkey apenas solicitam; o orquestrador controla a sessao.",
    ),
    VoiceActivationMode.WAKEWORD: VoiceActivationProfile(
        mode=VoiceActivationMode.WAKEWORD,
        availability=VoiceActivationAvailability.FUTURE,
        starts_listening=True,
        optional_subsystem=True,
        allowed_states=(AppState.IDLE,),
        requires_runtime_ready=True,
        requires_no_active_interaction=True,
        entry_event=AppEvent.VOICE_REQUESTED,
        termination_events=(
            AppEvent.STT_TEXT_READY,
            AppEvent.STT_NO_INPUT,
            AppEvent.STT_FAILED,
            AppEvent.SHUTDOWN_REQUESTED,
        ),
        owner="future_wake_subsystem",
        notes="Subsistema futuro e opcional. Nao faz parte do runtime oficial atual e nao deve rodar em daemon por padrao.",
    ),
    VoiceActivationMode.INTERRUPT: VoiceActivationProfile(
        mode=VoiceActivationMode.INTERRUPT,
        availability=VoiceActivationAvailability.AVAILABLE,
        starts_listening=False,
        optional_subsystem=False,
        allowed_states=(
            AppState.BOOTING,
            AppState.IDLE,
            AppState.LISTENING,
            AppState.PROCESSING,
            AppState.SPEAKING,
            AppState.ERROR,
        ),
        requires_runtime_ready=False,
        requires_no_active_interaction=False,
        entry_event=AppEvent.SHUTDOWN_REQUESTED,
        termination_events=(AppEvent.SHUTDOWN_REQUESTED,),
        owner="orchestrator",
        notes="Encerramento ou interrupcao operacional do runtime. Nao e wake word nem escuta continua.",
    ),
}


def get_voice_activation_profile(mode: VoiceActivationMode) -> VoiceActivationProfile:
    return OFFICIAL_VOICE_ACTIVATION_PROFILES[mode]


def evaluate_voice_activation_request(
    request: VoiceActivationRequest,
    *,
    app_state: AppState,
    runtime_ready: bool,
    has_active_interaction: bool,
    recovery_pending: bool,
) -> VoiceActivationDecision:
    profile = get_voice_activation_profile(request.mode)

    if profile.availability == VoiceActivationAvailability.FUTURE:
        return VoiceActivationDecision(
            request=request,
            accepted=False,
            rejection=VoiceActivationRejection.MODE_NOT_IMPLEMENTED,
            profile=profile,
            message="Modo de wake word reservado para subsistema futuro/opcional.",
        )

    if recovery_pending:
        return VoiceActivationDecision(
            request=request,
            accepted=False,
            rejection=VoiceActivationRejection.RECOVERY_IN_PROGRESS,
            profile=profile,
            message="Runtime em recuperacao; nova ativacao por voz bloqueada temporariamente.",
        )

    if profile.requires_runtime_ready and not runtime_ready:
        return VoiceActivationDecision(
            request=request,
            accepted=False,
            rejection=VoiceActivationRejection.RUNTIME_NOT_READY,
            profile=profile,
            message="Runtime ainda nao esta pronto para iniciar a ativacao por voz.",
        )

    if app_state not in profile.allowed_states:
        return VoiceActivationDecision(
            request=request,
            accepted=False,
            rejection=VoiceActivationRejection.INVALID_STATE,
            profile=profile,
            message=f"Modo {request.mode.value} indisponivel no estado {app_state.value}.",
        )

    if profile.requires_no_active_interaction and has_active_interaction:
        return VoiceActivationDecision(
            request=request,
            accepted=False,
            rejection=VoiceActivationRejection.INTERACTION_ACTIVE,
            profile=profile,
            message="Ja existe uma interacao ativa; a nova ativacao por voz foi rejeitada.",
        )

    return VoiceActivationDecision(
        request=request,
        accepted=True,
        rejection=VoiceActivationRejection.NONE,
        profile=profile,
        message="Ativacao aprovada pelo contrato oficial.",
    )
