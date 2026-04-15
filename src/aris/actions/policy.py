from __future__ import annotations

import re
import unicodedata

ALLOWED_COMMAND_IDS = {
    "open_browser",
    "open_youtube",
    "open_spotify",
    "open_known_site",
}

KNOWN_SITES = {
    "google": {"label": "Google", "url": "https://www.google.com"},
    "gmail": {"label": "Gmail", "url": "https://mail.google.com"},
    "github": {"label": "GitHub", "url": "https://github.com"},
    "youtube": {"label": "YouTube", "url": "https://www.youtube.com"},
    "wikipedia": {"label": "Wikipedia", "url": "https://pt.wikipedia.org"},
    "whatsapp web": {"label": "WhatsApp Web", "url": "https://web.whatsapp.com"},
}

_SITE_ALIASES = {
    "google": "google",
    "gmail": "gmail",
    "github": "github",
    "git hub": "github",
    "youtube": "youtube",
    "you tube": "youtube",
    "wikipedia": "wikipedia",
    "wiki": "wikipedia",
    "whatsapp": "whatsapp web",
    "whatsapp web": "whatsapp web",
}


def normalize_command_target(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def is_command_allowed(command_id: str | None) -> bool:
    return bool(command_id) and command_id in ALLOWED_COMMAND_IDS


def resolve_known_site(target: str) -> dict | None:
    normalized = normalize_command_target(target)
    alias = _SITE_ALIASES.get(normalized)
    if not alias:
        return None
    site = KNOWN_SITES.get(alias)
    if not site:
        return None
    return {"site_key": alias, **site}
