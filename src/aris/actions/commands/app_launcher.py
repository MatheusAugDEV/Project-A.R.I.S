from __future__ import annotations

import shutil
import subprocess

from src.aris.actions.commands.base import SafeCommand
from src.aris.actions.models import CommandMatch, CommandResult


def _can_run(cmd: list[str]) -> bool:
    return bool(cmd) and shutil.which(cmd[0]) is not None


def _spawn_first_available(candidates: list[list[str]]) -> bool:
    for candidate in candidates:
        if not _can_run(candidate):
            continue
        try:
            subprocess.Popen(
                candidate,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            continue
    return False


class SpotifyCommand(SafeCommand):
    command_id = "open_spotify"

    def execute(self, match: CommandMatch) -> CommandResult:
        candidates = [
            ["spotify"],
            ["spotify-launcher"],
            ["flatpak", "run", "com.spotify.Client"],
            ["snap", "run", "spotify"],
        ]

        if _spawn_first_available(candidates):
            return CommandResult(
                status="success",
                spoken_text="Abrindo o Spotify.",
                command_id=self.command_id,
            )

        return CommandResult(
            status="unavailable",
            spoken_text="Reconheci o comando para abrir o Spotify, mas ele nao parece estar disponivel neste sistema.",
            command_id=self.command_id,
        )
