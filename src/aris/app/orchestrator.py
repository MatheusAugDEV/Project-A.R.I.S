import threading
import time
from dataclasses import dataclass
from itertools import count
from typing import Optional

from src.aris.app.state_machine import AppEvent, AppState, InvalidTransitionError, StateMachine
from src.aris.app.ui_state import UIStateSnapshot
from src.aris.voice.activation import (
    VoiceActivationMode,
    VoiceActivationRequest,
    VoiceActivationSource,
    evaluate_voice_activation_request,
)

print("[INIT] Importando ARISOrb...")
from src.aris.ui.gui_orbe import ARISOrb
print("[INIT] ARISOrb importado!")

print("[INIT] Importando actions...")
from src.aris.actions.actions import (
    carregar_memoria,
    perguntar_ia,
    pesquisar_ia,
    resolver_acao_operacional,
    saudacao,
)
print("[INIT] Actions importadas!")

print("[INIT] Importando stt...")
from src.aris.voice.stt import ouvir, aquecer as aquecer_stt
print("[INIT] STT importado!")

print("[INIT] Importando brain...")
from src.aris.intents.brain import detectar_intencao, executar_intencao
print("[INIT] Brain importado!")

print("[INIT] Importando tts...")
from src.aris.voice.tts import falar
print("[INIT] TTS importado!")


memoria = {}
orb = None
_orb_lock = threading.RLock()
_interaction_lock = threading.RLock()
_gui_ativa = threading.Event()
_abrindo_gui = threading.Event()
_escuta_em_andamento = threading.Event()
_fala_em_andamento = threading.Event()
_recovery_pending = threading.Event()
_runtime_operational = threading.Event()
_state_machine = StateMachine()
_interaction_sequence = count(1)
_active_interaction_id = None
_active_context = None
_ui_lock = threading.RLock()
_ui_response_text = ""
_ui_audio_level = 0.0
_ui_error_message = None
_ui_status_override = None

_INTENTS_BUSCA = {
    "pesquisa_web": "web",
    "pesquisa_video": "video",
    "pesquisa_noticias": "noticias",
}

_OPERATIONAL_STATES = {
    AppState.IDLE,
    AppState.LISTENING,
    AppState.PROCESSING,
    AppState.SPEAKING,
}

_GUI_STATE_MAP = {
    AppState.BOOTING: "thinking",
    AppState.IDLE: "idle",
    AppState.LISTENING: "listening",
    AppState.PROCESSING: "thinking",
    AppState.SPEAKING: "speaking",
    AppState.ERROR: "thinking",
    AppState.SHUTTING_DOWN: "speaking",
}

_UI_STATUS_MAP = {
    AppState.BOOTING: "Inicializando runtime",
    AppState.IDLE: "Pronto para interagir",
    AppState.LISTENING: "Escutando",
    AppState.PROCESSING: "Processando",
    AppState.SPEAKING: "Respondendo",
    AppState.ERROR: "Erro recuperavel",
    AppState.SHUTTING_DOWN: "Encerrando",
}


@dataclass
class InteractionContext:
    interaction_id: int
    source: str
    phase: str
    input_text: str = ""
    response_text: str = ""
    close_after_speaking: bool = False


def _get_orb():
    with _orb_lock:
        return orb


def _set_orb(novo_orb):
    global orb
    with _orb_lock:
        orb = novo_orb


def _build_ui_snapshot() -> UIStateSnapshot:
    with _ui_lock:
        state = _state_machine.state
        status_text = _ui_status_override or _UI_STATUS_MAP[state]
        ready_for_interaction = state == AppState.IDLE and _runtime_operational.is_set()
        busy = not ready_for_interaction
        return UIStateSnapshot(
            state=state,
            visual_state=_GUI_STATE_MAP[state],
            status_text=status_text,
            input_enabled=ready_for_interaction,
            voice_trigger_enabled=ready_for_interaction,
            response_text=_ui_response_text,
            audio_level=_ui_audio_level,
            audio_meter_visible=(state == AppState.LISTENING),
            error_message=_ui_error_message,
            busy=busy,
        )


def _publish_ui_snapshot():
    atual = _get_orb()
    if atual is None:
        return
    atual.apply_snapshot(_build_ui_snapshot())


def _set_ui_response(texto: str):
    global _ui_response_text
    with _ui_lock:
        _ui_response_text = texto
    _publish_ui_snapshot()


def _set_ui_audio_level(level: float):
    global _ui_audio_level
    with _ui_lock:
        _ui_audio_level = max(0.0, min(float(level), 1.0))
    _publish_ui_snapshot()


def _set_ui_error(message: Optional[str]):
    global _ui_error_message
    with _ui_lock:
        _ui_error_message = message
    _publish_ui_snapshot()


def _set_ui_status(message: Optional[str]):
    global _ui_status_override
    with _ui_lock:
        _ui_status_override = message.strip() if isinstance(message, str) and message.strip() else None
    _publish_ui_snapshot()


def _has_active_interaction() -> bool:
    with _interaction_lock:
        return _active_interaction_id is not None


def _is_active_interaction(interaction_id: int) -> bool:
    with _interaction_lock:
        return _active_interaction_id == interaction_id


def _begin_interaction(source: str, *, phase: str, input_text: str = "") -> Optional[int]:
    global _active_interaction_id, _active_context

    with _interaction_lock:
        if _active_interaction_id is not None:
            return None

        interaction_id = next(_interaction_sequence)
        _active_interaction_id = interaction_id
        _active_context = InteractionContext(
            interaction_id=interaction_id,
            source=source,
            phase=phase,
            input_text=input_text,
        )
        print(f"[ARIS] Interacao {interaction_id} iniciada via {source}.")
        return interaction_id


def _update_interaction(interaction_id: int, **changes) -> bool:
    with _interaction_lock:
        if _active_interaction_id != interaction_id or _active_context is None:
            return False

        for campo, valor in changes.items():
            setattr(_active_context, campo, valor)
        return True


def _finish_interaction(interaction_id: int, reason: str) -> bool:
    global _active_interaction_id, _active_context

    with _interaction_lock:
        if _active_interaction_id != interaction_id:
            return False

        print(f"[ARIS] Interacao {interaction_id} finalizada: {reason}.")
        _active_interaction_id = None
        _active_context = None

    _escuta_em_andamento.clear()
    _set_ui_audio_level(0.0)
    return True


def _invalidate_active_interaction(reason: str):
    global _active_interaction_id, _active_context

    with _interaction_lock:
        if _active_interaction_id is None:
            return

        interaction_id = _active_interaction_id
        print(f"[ARIS] Interacao {interaction_id} invalidada: {reason}.")
        _active_interaction_id = None
        _active_context = None

    _escuta_em_andamento.clear()
    _set_ui_audio_level(0.0)


def _apply_gui_state():
    if _state_machine.state in _OPERATIONAL_STATES or _state_machine.state == AppState.SHUTTING_DOWN:
        _set_ui_error(None)
    _publish_ui_snapshot()


def _sync_runtime_operational(state: AppState):
    if state in _OPERATIONAL_STATES:
        _runtime_operational.set()
    else:
        _runtime_operational.clear()


def _transition(event: AppEvent, *, quiet: bool = False) -> bool:
    try:
        novo_estado = _state_machine.transition(event)
        print(f"[ARIS] Estado -> {novo_estado.value} ({event.value})")
        _sync_runtime_operational(novo_estado)
        _apply_gui_state()
        return True
    except InvalidTransitionError as exc:
        if not quiet:
            print(f"[ARIS] {exc}")
        return False


def _ao_nivel_audio(level: float):
    if _state_machine.state == AppState.LISTENING and _escuta_em_andamento.is_set():
        _set_ui_audio_level(level)


def _complete_boot_to_idle() -> bool:
    if _state_machine.state != AppState.BOOTING:
        return False
    if not _transition(AppEvent.BOOT_COMPLETED, quiet=True):
        return False
    _set_ui_status(None)
    _apply_gui_state()
    return True


def _schedule_runtime_recovery(stage: str, *, rewarm_stt: bool = False):
    if _state_machine.state != AppState.ERROR:
        return
    if _recovery_pending.is_set():
        return
    if not _gui_ativa.is_set():
        return

    _recovery_pending.set()
    _set_ui_status("Erro recuperavel. Tentando restabelecer o runtime")

    def _run():
        try:
            time.sleep(0.35)
            if _state_machine.state != AppState.ERROR:
                return

            _set_ui_status("Recuperando runtime")
            if not _transition(AppEvent.RECOVER_REQUESTED, quiet=True):
                return

            if rewarm_stt:
                _set_ui_status("Recuperando reconhecimento de voz")
                aquecer_stt()

            _set_ui_status("Retomando estado operacional")
            if not _complete_boot_to_idle():
                raise RuntimeError("Nao foi possivel concluir a recuperacao da FSM.")

            print(f"[ARIS] Runtime recuperado apos falha em {stage}.")
        except Exception as exc:
            print(f"[ARIS] Falha na recuperacao ({stage}): {type(exc).__name__}: {exc}")
            _set_ui_error(f"Falha na recuperacao: {type(exc).__name__}")
            _set_ui_status("Erro de recuperacao")
            if _state_machine.state == AppState.BOOTING:
                _transition(AppEvent.BOOT_FAILED, quiet=True)
        finally:
            _recovery_pending.clear()

    threading.Thread(target=_run, daemon=True).start()


def _handle_runtime_failure(
    stage: str,
    message: str,
    event: AppEvent,
    interaction_id: int,
    *,
    exc: Exception | None = None,
    rewarm_stt: bool = False,
):
    if exc is not None:
        print(f"[ARIS] Falha em {stage}: {type(exc).__name__}: {exc}")

    _set_ui_error(message)
    _set_ui_status("Erro recuperavel")
    transitioned = _transition(event, quiet=True)
    _finish_interaction(interaction_id, f"falha em {stage}")

    if transitioned and _state_machine.state == AppState.ERROR:
        _schedule_runtime_recovery(stage, rewarm_stt=rewarm_stt)


def _build_voice_request(source: VoiceActivationSource) -> VoiceActivationRequest:
    return VoiceActivationRequest(mode=VoiceActivationMode.ON_DEMAND, source=source)


def _solicitar_ativacao_por_voz(request: VoiceActivationRequest) -> bool:
    decision = evaluate_voice_activation_request(
        request,
        app_state=_state_machine.state,
        runtime_ready=_runtime_operational.is_set(),
        has_active_interaction=_has_active_interaction(),
        recovery_pending=_recovery_pending.is_set(),
    )

    if not decision.accepted:
        print(
            f"[ARIS] Ativacao por voz rejeitada "
            f"({request.activation_label}, motivo={decision.rejection.value})."
        )
        return False

    _iniciar_escuta_por_voz(request)
    return True


def sinalizar_ativacao_por_wakeword() -> bool:
    request = VoiceActivationRequest(
        mode=VoiceActivationMode.WAKEWORD,
        source=VoiceActivationSource.WAKEWORD_ENGINE,
    )
    decision = evaluate_voice_activation_request(
        request,
        app_state=_state_machine.state,
        runtime_ready=_runtime_operational.is_set(),
        has_active_interaction=_has_active_interaction(),
        recovery_pending=_recovery_pending.is_set(),
    )
    print(
        f"[ARIS] Wake word nao iniciada "
        f"({request.activation_label}, motivo={decision.rejection.value})."
    )
    return False


def _falar_async(texto: str, ao_final=None, ao_erro=None):
    def _run():
        _fala_em_andamento.set()
        erro = None
        try:
            falar(texto)
        except Exception as exc:
            erro = exc
            print(f"[ARIS] Falha TTS: {type(exc).__name__}: {exc}")
        finally:
            _fala_em_andamento.clear()
            callback = ao_erro if erro is not None else ao_final
            if callback:
                try:
                    if erro is not None:
                        callback(erro)
                    else:
                        callback()
                except Exception as e:
                    print(f"[ARIS] Erro no callback de audio: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _fechar_janela():
    _invalidate_active_interaction("encerramento solicitado")
    _transition(AppEvent.SHUTDOWN_REQUESTED, quiet=True)
    atual = _get_orb()
    if atual is None:
        return
    print("[ARIS] Fechando janela...")
    atual.stop()


def _concluir_fala(interaction_id: int):
    if not _is_active_interaction(interaction_id):
        print(f"[ARIS] Callback TTS ignorado para interacao antiga {interaction_id}.")
        return

    _transition(AppEvent.TTS_COMPLETED, quiet=True)
    _finish_interaction(interaction_id, "tts concluido")


def _concluir_fala_e_encerrar(interaction_id: int):
    if not _is_active_interaction(interaction_id):
        print(f"[ARIS] Callback TTS ignorado para interacao antiga {interaction_id}.")
        return

    _transition(AppEvent.TTS_COMPLETED, quiet=True)
    _finish_interaction(interaction_id, "tts concluido com encerramento")
    _fechar_janela()


def _tratar_falha_tts(interaction_id: int, exc: Exception, *, close_after_failure: bool = False):
    if not _is_active_interaction(interaction_id):
        print(f"[ARIS] Falha TTS ignorada para interacao antiga {interaction_id}.")
        return

    if close_after_failure:
        _set_ui_error("Falha ao reproduzir o audio de encerramento.")
        _finish_interaction(interaction_id, "falha de tts com encerramento")
        _fechar_janela()
        return

    _handle_runtime_failure(
        "tts",
        "Falha na sintese ou reproducao de voz.",
        AppEvent.TTS_FAILED,
        interaction_id,
        exc=exc,
        rewarm_stt=False,
    )


def _executar_processamento(interaction_id: int, texto: str):
    if not _is_active_interaction(interaction_id):
        print(f"[ARIS] Processamento descartado para interacao antiga {interaction_id}.")
        return

    _update_interaction(interaction_id, phase="processing", input_text=texto)
    _set_ui_response("")
    _apply_gui_state()

    try:
        intencao = detectar_intencao(texto)
        decision = resolver_acao_operacional(texto, local_intent=intencao)
        if decision.kind in {"command", "command_unsupported"}:
            resposta = decision.command_result.spoken_text if decision.command_result else "Nao consegui tratar esse comando."
            intencao = "comando_seguro"
        elif decision.kind == "local_intent" and decision.local_intent:
            intencao = decision.local_intent
            resposta = executar_intencao(decision.local_intent, texto)
        elif decision.kind == "search" and decision.search_request is not None:
            intencao = decision.local_intent or "pesquisa_web"
            resposta = pesquisar_ia(texto, memoria, decision.search_request.search_type)
        else:
            intencao = None
            resposta = perguntar_ia(texto, memoria)
    except Exception as exc:
        if _is_active_interaction(interaction_id):
            _handle_runtime_failure(
                "processing",
                "Falha no processamento do comando.",
                AppEvent.PROCESSING_FAILED,
                interaction_id,
                exc=exc,
                rewarm_stt=False,
            )
        return

    if not _is_active_interaction(interaction_id):
        print(f"[ARIS] Resultado descartado para interacao antiga {interaction_id}.")
        return

    _update_interaction(
        interaction_id,
        phase="speaking",
        response_text=resposta,
        close_after_speaking=(intencao == "sair"),
    )
    if not _transition(AppEvent.PROCESSING_COMPLETED, quiet=True):
        _finish_interaction(interaction_id, "processamento concluido sem transicao valida")
        print(f"[ARIS] Resposta descartada para interacao {interaction_id} por estado invalido.")
        return

    _set_ui_response(resposta)
    print(f"[ARIS]: {resposta}")

    if intencao == "sair":
        _falar_async(
            resposta,
            ao_final=lambda: _concluir_fala_e_encerrar(interaction_id),
            ao_erro=lambda exc: _tratar_falha_tts(interaction_id, exc, close_after_failure=True),
        )
        return

    _falar_async(
        resposta,
        ao_final=lambda: _concluir_fala(interaction_id),
        ao_erro=lambda exc: _tratar_falha_tts(interaction_id, exc),
    )


def _submeter_texto_para_processamento(
    interaction_id: int,
    texto: str,
    *,
    ready_event: AppEvent,
    rejection_reason: str,
) -> bool:
    texto = (texto or "").strip()
    if not texto:
        _finish_interaction(interaction_id, f"{rejection_reason}: texto vazio")
        return False

    _update_interaction(interaction_id, phase="processing", input_text=texto)
    if not _transition(ready_event, quiet=True):
        _finish_interaction(interaction_id, rejection_reason)
        return False

    _executar_processamento(interaction_id, texto)
    return True


def processar_e_responder(texto: str):
    texto = (texto or "").strip()
    if not texto:
        return

    if _has_active_interaction():
        print("[ARIS] Entrada manual ignorada: ja existe interacao ativa.")
        return

    interaction_id = _begin_interaction("manual", phase="processing", input_text=texto)
    if interaction_id is None:
        print("[ARIS] Nao foi possivel iniciar interacao manual.")
        return

    if not _submeter_texto_para_processamento(
        interaction_id,
        texto,
        ready_event=AppEvent.MANUAL_TEXT_RECEIVED,
        rejection_reason="entrada manual rejeitada pela FSM",
    ):
        print(f"[ARIS] Entrada manual ignorada no estado {_state_machine.state.value}.")


def solicitar_escuta_por_voz():
    _solicitar_ativacao_por_voz(_build_voice_request(VoiceActivationSource.HOTKEY_F8))


def _iniciar_escuta_por_voz(request: VoiceActivationRequest):
    interaction_id = _begin_interaction(request.activation_label, phase="listening")
    if interaction_id is None:
        print("[ARIS] Nao foi possivel iniciar interacao por voz.")
        return

    if not _transition(AppEvent.VOICE_REQUESTED, quiet=True):
        _finish_interaction(interaction_id, "pedido de voz rejeitado pela FSM")
        print(f"[ARIS] Pedido de voz ignorado no estado {_state_machine.state.value}.")
        return

    _escuta_em_andamento.set()
    _set_ui_response("")
    _apply_gui_state()

    def _ao_receber_texto(texto: str):
        if not _is_active_interaction(interaction_id):
            print(f"[ARIS] Callback STT ignorado para interacao antiga {interaction_id}.")
            return

        try:
            _escuta_em_andamento.clear()
            _submeter_texto_para_processamento(
                interaction_id,
                texto,
                ready_event=AppEvent.STT_TEXT_READY,
                rejection_reason="retorno STT sem transicao valida",
            )
        finally:
            _escuta_em_andamento.clear()

    def _run():
        try:
            _ao_nivel_audio(0.0)
            texto = ouvir(
                level_callback=_ao_nivel_audio,
                session_id=interaction_id,
                activation_label=request.activation_label,
            )
            if not _is_active_interaction(interaction_id):
                print(f"[ARIS] Resultado STT descartado para interacao antiga {interaction_id}.")
                return
            if texto:
                _ao_receber_texto(texto)
            else:
                _escuta_em_andamento.clear()
                _transition(AppEvent.STT_NO_INPUT, quiet=True)
                _set_ui_audio_level(0.0)
                _finish_interaction(interaction_id, "stt sem entrada")
        except Exception as e:
            if not _is_active_interaction(interaction_id):
                print(f"[ARIS] Falha STT descartada da interacao antiga {interaction_id}: {e}")
                return
            _escuta_em_andamento.clear()
            _handle_runtime_failure(
                "stt",
                "Falha na captura ou transcricao de voz.",
                AppEvent.STT_FAILED,
                interaction_id,
                exc=e,
                rewarm_stt=True,
            )
        finally:
            _ao_nivel_audio(0.0)

    threading.Thread(target=_run, daemon=True).start()


def _criar_orb():
    novo_orb = ARISOrb()

    def ouvir_e_processar():
        _solicitar_ativacao_por_voz(_build_voice_request(VoiceActivationSource.GUI_BUTTON))

    novo_orb.on_input = processar_e_responder
    novo_orb.on_voice = ouvir_e_processar
    return novo_orb


def _executar_janela():
    _abrindo_gui.set()
    try:
        atual = _criar_orb()
        _set_orb(atual)
        _gui_ativa.set()
        _set_ui_response("")
        _set_ui_audio_level(0.0)
        _set_ui_status("Preparando interface")
        _publish_ui_snapshot()
        if _state_machine.state == AppState.BOOTING and not _complete_boot_to_idle():
            raise RuntimeError("Nao foi possivel finalizar o boot do runtime.")

        atual.run_blocking()
    finally:
        _invalidate_active_interaction("janela encerrada")
        _transition(AppEvent.SHUTDOWN_REQUESTED, quiet=True)
        _abrindo_gui.clear()
        _gui_ativa.clear()
        _set_orb(None)
        print("[ARIS] Janela encerrada.")


def run_manual_runtime():
    global memoria

    try:
        _runtime_operational.clear()
        _recovery_pending.clear()
        _set_ui_error(None)
        _set_ui_status("Carregando memoria")
        print("[ARIS] Carregando memoria...")
        memoria = carregar_memoria()
        print("[ARIS] Memoria carregada!")
        _set_ui_status("Aquecendo reconhecimento de voz")
        print("[ARIS] Aquecendo reconhecimento de voz...")
        aquecer_stt()
        _set_ui_status("Abrindo interface")
        print("[ARIS] Modo manual ativo. Sem escuta em segundo plano.")
        print("[ARIS] Abrindo interface...")
        _executar_janela()

    except KeyboardInterrupt:
        _invalidate_active_interaction("interrupcao por teclado")
        _set_ui_status("Encerrando")
        _transition(AppEvent.SHUTDOWN_REQUESTED, quiet=True)
        print("[ARIS] Encerrando por teclado...")
    except Exception as e:
        if _state_machine.state == AppState.BOOTING:
            _set_ui_error(f"Falha no boot: {type(e).__name__}")
            _set_ui_status("Falha no boot")
            _transition(AppEvent.BOOT_FAILED, quiet=True)
        print(f"[ERRO] {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        raise
