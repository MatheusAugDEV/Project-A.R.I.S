from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AIRequest:
    question: str
    memory: dict
    original_text: str | None = None


@dataclass(frozen=True)
class SearchRequest:
    query: str
    search_type: str = "web"
    original_text: str = ""


@dataclass(frozen=True)
class ActionResponse:
    text: str
    source: str


@dataclass(frozen=True)
class Interpretation:
    kind: str = "conversa"
    target: str = "usuario"
    goal: str = "responder"


@dataclass(frozen=True)
class CommandMatch:
    command_id: str | None
    raw_text: str
    target: str = ""
    normalized_target: str = ""
    command_like: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult:
    status: str
    spoken_text: str
    command_id: str | None = None
    handled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionDecision:
    kind: str
    raw_text: str
    local_intent: str | None = None
    command_match: CommandMatch | None = None
    search_request: SearchRequest | None = None
    command_result: CommandResult | None = None
