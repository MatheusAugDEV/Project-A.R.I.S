import threading
from dataclasses import dataclass
from itertools import count
from typing import Optional

from src.aris.app.state_machine import AppEvent, AppState, InvalidTransitionError, StateMachine
from src.aris.app.ui_state import UIStateSnapshot

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
_state_machine = StateMachine()
_interaction_sequence = count(1)
_active_interaction_id = None
_active_context = None
_ui_lock = threading.RLock()
_ui_response_text = ""
_ui_audio_level = 0.0
_ui_error_message = None

_INTENTS_BUSCA = {
    "pesquisa_web": "web",
    "pesquisa_video": "video",
    "pesquisa_noticias": "noticias",
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
    AppState.BOOTING: "Inicializando",
    AppState.IDLE: "Aguardando comando",
    AppState.LISTENING: "Escutando",
    AppState.PROCESSING: "Processando",
    AppState.SPEAKING: "Respondendo",
    AppState.ERROR: "Erro",
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
        busy = state != AppState.IDLE
        return UIStateSnapshot(
            state=state,
            visual_state=_GUI_STATE_MAP[state],
            status_text=_UI_STATUS_MAP[state],
            input_enabled=(state == AppState.IDLE),
            voice_trigger_enabled=(state == AppState.IDLE),
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
    if _state_machine.state != AppState.ERROR:
        _set_ui_error(None)
    _publish_ui_snapshot()


def _transition(event: AppEvent, *, quiet: bool = False) -> bool:
    try:
        novo_estado = _state_machine.transition(event)
        print(f"[ARIS] Estado -> {novo_estado.value} ({event.value})")
        _apply_gui_state()
        return True
    except InvalidTransitionError as exc:
        if not quiet:
            print(f"[ARIS] {exc}")
        return False


def _ao_nivel_audio(level: float):
    if _state_machine.state == AppState.LISTENING and _escuta_em_andamento.is_set():
        _set_ui_audio_level(level)


def _falar_async(texto: str, ao_final=None):
    def _run():
        _fala_em_andamento.set()
        try:
            falar(texto)
        finally:
            _fala_em_andamento.clear()
            if ao_final:
                try:
                    ao_final()
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
    except Exception:
        if _is_active_interaction(interaction_id):
            _set_ui_error("Falha no processamento do comando.")
            _transition(AppEvent.PROCESSING_FAILED, quiet=True)
            _finish_interaction(interaction_id, "falha de processamento")
        raise

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
        _falar_async(resposta, ao_final=lambda: _concluir_fala_e_encerrar(interaction_id))
        return

    _falar_async(resposta, ao_final=lambda: _concluir_fala(interaction_id))


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
    if _state_machine.state != AppState.IDLE:
        print(f"[ARIS] Pedido de voz ignorado no estado {_state_machine.state.value}.")
        return

    _iniciar_escuta_por_voz()


def _iniciar_escuta_por_voz():
    if _has_active_interaction():
        print("[ARIS] Pedido de voz ignorado: ja existe interacao ativa.")
        return

    interaction_id = _begin_interaction("voice", phase="listening")
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
            texto = ouvir(level_callback=_ao_nivel_audio, session_id=interaction_id)
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
            _set_ui_error("Falha na captura ou transcricao de voz.")
            _transition(AppEvent.STT_FAILED, quiet=True)
            _finish_interaction(interaction_id, "falha de stt")
            raise
        finally:
            _ao_nivel_audio(0.0)

    threading.Thread(target=_run, daemon=True).start()


def _criar_orb():
    novo_orb = ARISOrb()

    def ouvir_e_processar():
        solicitar_escuta_por_voz()

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
        _publish_ui_snapshot()

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
        print("[ARIS] Carregando memoria...")
        memoria = carregar_memoria()
        print("[ARIS] Memoria carregada!")
        print("[ARIS] Aquecendo reconhecimento de voz...")
        aquecer_stt()
        _transition(AppEvent.BOOT_COMPLETED, quiet=True)
        print("[ARIS] Modo manual ativo. Sem escuta em segundo plano.")
        print("[ARIS] Abrindo interface...")
        _executar_janela()

    except KeyboardInterrupt:
        _invalidate_active_interaction("interrupcao por teclado")
        _transition(AppEvent.SHUTDOWN_REQUESTED, quiet=True)
        print("[ARIS] Encerrando por teclado...")
    except Exception as e:
        if _state_machine.state == AppState.BOOTING:
            _set_ui_error(f"Falha no boot: {type(e).__name__}")
            _transition(AppEvent.BOOT_FAILED, quiet=True)
        print(f"[ERRO] {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        raise
