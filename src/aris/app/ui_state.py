from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.aris.app.state_machine import AppState


@dataclass(frozen=True)
class UIStateSnapshot:
    state: AppState
    visual_state: str
    status_text: str
    input_enabled: bool
    voice_trigger_enabled: bool
    response_text: str
    audio_level: float
    audio_meter_visible: bool
    error_message: Optional[str]
    busy: bool
