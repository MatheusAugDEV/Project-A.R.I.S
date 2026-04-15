from __future__ import annotations

import threading

_history: list[dict[str, str]] = []
_history_lock = threading.RLock()


def append_history(role: str, content: str) -> None:
    role = (role or "").strip()
    content = " ".join(str(content or "").split()).strip()
    if role not in {"user", "assistant"} or not content:
        return

    with _history_lock:
        _history.append({"role": role, "content": content})
        del _history[:-32]


def get_history_window(limit: int = 16) -> list[dict[str, str]]:
    limit = max(1, int(limit))
    with _history_lock:
        return list(_history[-limit:])
