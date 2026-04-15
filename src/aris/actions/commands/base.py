from __future__ import annotations

from abc import ABC, abstractmethod

from src.aris.actions.models import CommandMatch, CommandResult


class SafeCommand(ABC):
    command_id: str

    @abstractmethod
    def execute(self, match: CommandMatch) -> CommandResult:
        raise NotImplementedError
