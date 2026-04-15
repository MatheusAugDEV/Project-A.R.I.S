from __future__ import annotations

import shutil
import subprocess
import webbrowser

from src.aris.actions.commands.base import SafeCommand
from src.aris.actions.models import CommandMatch, CommandResult


def _open_url(url: str) -> bool:
    try:
        if webbrowser.open(url, new=2):
            return True
    except Exception:
        pass

    if shutil.which("xdg-open"):
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    return False


class BrowserCommand(SafeCommand):
    command_id = "open_browser"

    def execute(self, match: CommandMatch) -> CommandResult:
        if _open_url("https://www.google.com"):
            return CommandResult(
                status="success",
                spoken_text="Abrindo o navegador.",
                command_id=self.command_id,
            )
        return CommandResult(
            status="failed",
            spoken_text="Nao consegui abrir o navegador agora.",
            command_id=self.command_id,
        )


class YouTubeCommand(SafeCommand):
    command_id = "open_youtube"

    def execute(self, match: CommandMatch) -> CommandResult:
        if _open_url("https://www.youtube.com"):
            return CommandResult(
                status="success",
                spoken_text="Abrindo o YouTube.",
                command_id=self.command_id,
            )
        return CommandResult(
            status="failed",
            spoken_text="Nao consegui abrir o YouTube agora.",
            command_id=self.command_id,
        )


class KnownSiteCommand(SafeCommand):
    command_id = "open_known_site"

    def execute(self, match: CommandMatch) -> CommandResult:
        url = match.metadata.get("url", "")
        label = match.metadata.get("label", "o site")
        if not url:
            return CommandResult(
                status="not_supported",
                spoken_text="Esse site nao esta no meu catalogo seguro.",
                command_id=self.command_id,
            )

        if _open_url(url):
            return CommandResult(
                status="success",
                spoken_text=f"Abrindo {label}.",
                command_id=self.command_id,
                metadata={"url": url, "label": label},
            )

        return CommandResult(
            status="failed",
            spoken_text=f"Nao consegui abrir {label} agora.",
            command_id=self.command_id,
            metadata={"url": url, "label": label},
        )
