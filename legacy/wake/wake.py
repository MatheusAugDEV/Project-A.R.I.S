"""
Fachada de wake word do ARIS - COMPLETAMENTE DESATIVADO.
Este modulo foi desabilitado permanentemente a pedido do usuario.
"""

from __future__ import annotations

import threading

# Variavel global para compatibilidade com tts.py
_tts_ativo = False
_stop_evt = threading.Event()
_listener_thread = None
_callback = None
_level_callback = None


def start(callback, level_callback=None):
    """DESATIVADO - Nao faz nada."""
    print("[Wake] Sistema de wake word DESATIVADO permanentemente.")
    return


def stop(join_timeout: float = 2.0):
    """DESATIVADO - Nao faz nada."""
    return


def _loop(threshold: float):
    """DESATIVADO - Nao faz nada."""
    pass