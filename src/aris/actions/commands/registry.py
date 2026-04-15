from __future__ import annotations

import re

from src.aris.actions.commands.app_launcher import SpotifyCommand
from src.aris.actions.commands.web_launcher import BrowserCommand, KnownSiteCommand, YouTubeCommand
from src.aris.actions.models import CommandMatch, CommandResult
from src.aris.actions.policy import is_command_allowed, normalize_command_target, resolve_known_site

_COMMANDS = {
    "open_browser": BrowserCommand(),
    "open_youtube": YouTubeCommand(),
    "open_known_site": KnownSiteCommand(),
    "open_spotify": SpotifyCommand(),
}

_OPEN_PREFIX = re.compile(r"^(abra|abrir|abre|open)\b", re.IGNORECASE)


def resolve_command(text: str) -> CommandMatch | None:
    raw_text = (text or "").strip()
    if not raw_text:
        return None

    normalized = normalize_command_target(raw_text)

    if re.match(r"^(abra|abrir|abre|open)\s+(o\s+)?youtube\b", normalized):
        return CommandMatch(
            command_id="open_youtube",
            raw_text=raw_text,
            target="youtube",
            normalized_target="youtube",
            command_like=True,
        )

    if re.match(r"^(abra|abrir|abre|open)\s+(o\s+)?(navegador|browser)\b", normalized):
        return CommandMatch(
            command_id="open_browser",
            raw_text=raw_text,
            target="navegador",
            normalized_target="browser",
            command_like=True,
        )

    if re.match(r"^(abra|abrir|abre|open)\s+(o\s+)?spotify\b", normalized):
        return CommandMatch(
            command_id="open_spotify",
            raw_text=raw_text,
            target="spotify",
            normalized_target="spotify",
            command_like=True,
        )

    site_match = re.match(
        r"^(abra|abrir|abre|open)\s+(o\s+)?(site|pagina)?\s*(do|da|de)?\s*(?P<site>.+)$",
        normalized,
    )
    if site_match:
        site_target = site_match.group("site").strip()
        resolved_site = resolve_known_site(site_target)
        if resolved_site:
            return CommandMatch(
                command_id="open_known_site",
                raw_text=raw_text,
                target=site_target,
                normalized_target=normalize_command_target(site_target),
                command_like=True,
                metadata=resolved_site,
            )
        if _OPEN_PREFIX.match(normalized):
            return CommandMatch(
                command_id=None,
                raw_text=raw_text,
                target=site_target,
                normalized_target=normalize_command_target(site_target),
                command_like=True,
            )

    if _OPEN_PREFIX.match(normalized):
        target = re.sub(r"^(abra|abrir|abre|open)\s+", "", normalized).strip()
        return CommandMatch(
            command_id=None,
            raw_text=raw_text,
            target=target,
            normalized_target=normalize_command_target(target),
            command_like=True,
        )

    return None


def execute_command(match: CommandMatch) -> CommandResult:
    if not match.command_like:
        return CommandResult(status="not_supported", spoken_text="", command_id=None, handled=False)

    if not match.command_id:
        alvo = match.target or "esse pedido"
        return CommandResult(
            status="not_supported",
            spoken_text=f"Esse comando parece valido, mas '{alvo}' ainda nao esta no meu catalogo seguro.",
            command_id=None,
        )

    if not is_command_allowed(match.command_id):
        return CommandResult(
            status="not_supported",
            spoken_text="Esse comando nao esta permitido no catalogo atual do ARIS.",
            command_id=match.command_id,
        )

    command = _COMMANDS.get(match.command_id)
    if command is None:
        return CommandResult(
            status="not_supported",
            spoken_text="Esse comando foi reconhecido, mas ainda nao esta implementado.",
            command_id=match.command_id,
        )

    return command.execute(match)
