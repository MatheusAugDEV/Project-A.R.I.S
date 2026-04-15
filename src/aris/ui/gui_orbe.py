
import math
import random
import threading
import time
import subprocess
import os
import pygame

from src.aris.app.state_machine import AppState
from src.aris.app.ui_state import UIStateSnapshot

WIDTH, HEIGHT = 900, 960
FPS           = 60
CX, CY        = WIDTH // 2, 410
BG            = (2, 6, 10)

STATES = {
    "idle":      {"speed": 0.4,  "pulse": 0.03, "node_count": 60,  "edge_prob": 0.18, "color": (0, 200, 220), "glow": 0.6,  "label": "standby"},
    "listening": {"speed": 1.2,  "pulse": 0.12, "node_count": 80,  "edge_prob": 0.22, "color": (0, 229, 255), "glow": 1.0,  "label": "listening"},
    "thinking":  {"speed": 2.5,  "pulse": 0.07, "node_count": 100, "edge_prob": 0.30, "color": (0, 160, 255), "glow": 1.2,  "label": "processing"},
    "speaking":  {"speed": 0.9,  "pulse": 0.10, "node_count": 70,  "edge_prob": 0.20, "color": (0, 220, 200), "glow": 0.9,  "label": "responding"},
}

STATE_META = {
    AppState.BOOTING: {"label": "BOOTING", "accent": (255, 184, 82), "hint": "Inicializando modulos e interface"},
    AppState.IDLE: {"label": "PRONTO", "accent": (90, 232, 235), "hint": "Texto e F8 disponiveis"},
    AppState.LISTENING: {"label": "ESCUTA ATIVA", "accent": (74, 240, 255), "hint": "Fale agora perto do notebook"},
    AppState.PROCESSING: {"label": "ANALISANDO", "accent": (80, 174, 255), "hint": "Interpretando comando e preparando resposta"},
    AppState.SPEAKING: {"label": "RESPONDENDO", "accent": (74, 225, 196), "hint": "ARIS esta falando"},
    AppState.ERROR: {"label": "ERRO", "accent": (255, 104, 104), "hint": "Falha na ultima etapa do fluxo"},
    AppState.SHUTTING_DOWN: {"label": "ENCERRANDO", "accent": (255, 176, 92), "hint": "Finalizando sessao"},
}

def lerp(a, b, k):
    return a + (b - a) * k

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class ARISOrb:
    def __init__(self, on_input=None):
        self._snapshot_lock = threading.RLock()
        self.app_state      = AppState.IDLE
        self.state         = "idle"
        self.running       = False
        self._thread       = None
        self.t             = 0.0
        self.nodes         = []
        self.cur_color     = list(STATES["idle"]["color"])
        self.cur_speed     = STATES["idle"]["speed"]
        self.cur_pulse     = STATES["idle"]["pulse"]
        self.cur_glow      = STATES["idle"]["glow"]
        self.uptime_start  = time.time()
        self.on_input      = on_input
        self.on_voice      = None
        self.input_text    = ""
        self.last_response = ""
        self._input_active = True
        self.audio_level   = 0.0
        self.audio_level_smooth = 0.0
        self.status_text = "Aguardando comando"
        self.input_enabled = True
        self.voice_trigger_enabled = True
        self.audio_meter_visible = False
        self.error_message = None
        self.busy = False
        self._build_nodes("idle")

    def apply_snapshot(self, snapshot: UIStateSnapshot):
        with self._snapshot_lock:
            self.app_state = snapshot.state
            self.state = snapshot.visual_state
            self.status_text = snapshot.status_text
            self.input_enabled = snapshot.input_enabled
            self.voice_trigger_enabled = snapshot.voice_trigger_enabled
            self.last_response = snapshot.response_text
            self.audio_level = clamp(float(snapshot.audio_level), 0.0, 1.0)
            self.audio_meter_visible = snapshot.audio_meter_visible
            self.error_message = snapshot.error_message
            self.busy = snapshot.busy
            self._build_nodes(snapshot.visual_state)

    def set_state(self, state: str):
        if state in STATES:
            with self._snapshot_lock:
                self.state = state
                self._build_nodes(state)

    def set_response(self, text: str):
        with self._snapshot_lock:
            self.last_response = text

    def set_audio_level(self, level: float):
        with self._snapshot_lock:
            self.audio_level = clamp(float(level), 0.0, 1.0)

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def run_blocking(self):
        self.running = True
        self._run()

    def _build_nodes(self, state):
        count = STATES[state]["node_count"]
        self.nodes = []
        for _ in range(count):
            theta = random.uniform(0, math.pi * 2)
            phi   = math.acos(2 * random.random() - 1)
            r     = random.uniform(70, 115)
            self.nodes.append({
                "bx": CX + r * math.sin(phi) * math.cos(theta),
                "by": CY + r * math.sin(phi) * math.sin(theta),
                "bz": r * math.cos(phi),
                "ox": random.uniform(-4, 4),
                "oy": random.uniform(-4, 4),
                "vx": random.uniform(-0.3, 0.3),
                "vy": random.uniform(-0.3, 0.3),
                "size": random.uniform(0.8, 2.6),
            })

    def _wrap_text(self, text, font, max_width):
        words = text.split()
        lines, current = [], ""
        for word in words:
            test = f"{current} {word}".strip()
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _run(self):
        pygame.mixer.pre_init(0, 0, 0, 0)  # desabilita mixer — áudio via sounddevice
        pygame.init()
        pygame.mixer.quit()
        screen     = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE)
        fullscreen = False
        pygame.display.set_caption("ARIS")
        clock = pygame.time.Clock()

        def _clipboard_get() -> str:
            cmds = [
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"],
                ["wl-paste", "--no-newline"],
            ]
            for cmd in cmds:
                try:
                    return subprocess.check_output(
                        cmd, stderr=subprocess.DEVNULL, timeout=1
                    ).decode("utf-8", errors="ignore")
                except Exception:
                    continue
            return ""

        def _clipboard_set(text: str):
            cmds = [
                (["xclip", "-selection", "clipboard"], text.encode("utf-8")),
                (["xsel", "--clipboard", "--input"],   text.encode("utf-8")),
                (["wl-copy"],                          text.encode("utf-8")),
            ]
            for cmd, inp in cmds:
                try:
                    subprocess.run(cmd, input=inp, stderr=subprocess.DEVNULL,
                                   timeout=1, check=True)
                    return
                except Exception:
                    continue

        font_micro = pygame.font.SysFont("monospace", 11)
        font_title = pygame.font.SysFont("monospace", 52)
        font_input = pygame.font.SysFont("monospace", 15)
        font_resp  = pygame.font.SysFont("monospace", 13)

        pygame.key.start_text_input()

        cursor_tick    = 0
        current_cursor = pygame.SYSTEM_CURSOR_ARROW
        # Input box geometry
        box_pad  = 72
        box_x    = box_pad
        box_w    = WIDTH - box_pad * 2
        box_h    = 48
        box_y    = HEIGHT - 86
        box_r    = box_h // 2          # border-radius = pill shape

        # Send button (circle inside box, right side)
        btn_size = 30
        btn_cx   = box_x + box_w - btn_size // 2 - 9
        btn_cy   = box_y + box_h // 2
        btn_rect = pygame.Rect(btn_cx - btn_size // 2, btn_cy - btn_size // 2, btn_size, btn_size)

        input_rect = pygame.Rect(box_x, box_y, box_w - btn_size - 18, box_h)

        def _send():
            txt = self.input_text.strip()
            if txt and self.on_input and self.input_enabled:
                threading.Thread(target=self.on_input, args=(txt,), daemon=True).start()
                self.input_text = ""

        def _do_paste():
            txt = _clipboard_get().replace('\n', ' ').strip()
            if txt:
                espaco = 120 - len(self.input_text)
                self.input_text += txt[:espaco]
                return True
            return False

        # menu de contexto — lista de (label, fn)
        CTX_W      = 200
        CTX_ITEM_H = 34
        CTX_PAD    = 5
        CTX_R      = 8
        ctx = {"visible": False, "x": 0, "y": 0, "items": []}
        resp_rect  = None   # atualizado a cada frame

        def _abrir_ctx(pos, items):
            n = len(items)
            mh = n * CTX_ITEM_H + CTX_PAD * 2
            mx = min(pos[0], WIDTH  - CTX_W - 4)
            my = min(pos[1], HEIGHT - mh    - 4)
            ctx["visible"] = True
            ctx["x"] = mx
            ctx["y"] = my
            ctx["items"] = items

        def _ctx_item_rect(i):
            return pygame.Rect(ctx["x"], ctx["y"] + CTX_PAD + i * CTX_ITEM_H, CTX_W, CTX_ITEM_H)

        while self.running:
            mouse_pos  = pygame.mouse.get_pos()
            over_input = input_rect.collidepoint(mouse_pos)
            over_btn   = btn_rect.collidepoint(mouse_pos)
            over_resp  = resp_rect is not None and resp_rect.collidepoint(mouse_pos)
            over_ctx   = ctx["visible"] and any(
                             _ctx_item_rect(i).collidepoint(mouse_pos)
                             for i in range(len(ctx["items"])))

            desired = pygame.SYSTEM_CURSOR_HAND if (over_btn or over_ctx) else (
                      pygame.SYSTEM_CURSOR_IBEAM if over_input else
                      pygame.SYSTEM_CURSOR_ARROW)
            if desired != current_cursor:
                pygame.mouse.set_cursor(desired)
                current_cursor = desired

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                 self.running = False

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    if over_resp and self.last_response:
                        items = [
                            ("Copiar resposta", lambda: _clipboard_set(self.last_response)),
                        ]
                        _abrir_ctx(event.pos, items)
                    elif over_input or over_btn:
                        items = []
                        items.append(("Colar",   _do_paste))
                        if self.input_text:
                            items.append(("Copiar entrada", lambda: _clipboard_set(self.input_text)))
                            items.append(("Limpar",         lambda: setattr(self, 'input_text', '')))
                        _abrir_ctx(event.pos, items)
                    else:
                        ctx["visible"] = False

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if ctx["visible"]:
                        for i, (_, fn) in enumerate(ctx["items"]):
                            if _ctx_item_rect(i).collidepoint(mouse_pos):
                                fn()
                                cursor_tick = 0
                                break
                        ctx["visible"] = False
                    elif over_btn:
                        _send()
                        cursor_tick = 0

                elif event.type == pygame.TEXTINPUT:
                    if len(self.input_text) < 120:
                        espaco = 120 - len(self.input_text)
                        self.input_text += event.text[:espaco]
                        cursor_tick = 0

                elif event.type == pygame.KEYDOWN:
                    mods = pygame.key.get_mods()
                    if event.key == pygame.K_ESCAPE:
                        if fullscreen:
                            pygame.display.toggle_fullscreen()
                            fullscreen = False
                        else:
                            self.running = False
                    elif event.key == pygame.K_F11:
                        pygame.display.toggle_fullscreen()
                        fullscreen = not fullscreen
                    elif event.key == pygame.K_F8:
                        if self.on_voice and self.voice_trigger_enabled:
                            threading.Thread(target=self.on_voice, daemon=True).start()
                    elif event.key == pygame.K_RETURN:
                        _send()
                        cursor_tick = 0
                    elif event.key == pygame.K_BACKSPACE:
                        if mods & pygame.KMOD_CTRL:
                            parts = self.input_text.rstrip().rsplit(' ', 1)
                            self.input_text = parts[0] + ' ' if len(parts) > 1 else ''
                        else:
                            self.input_text = self.input_text[:-1]
                        cursor_tick = 0
                    elif event.key == pygame.K_v and mods & pygame.KMOD_CTRL:
                        if _do_paste():
                            cursor_tick = 0
                    elif event.key == pygame.K_c and mods & pygame.KMOD_CTRL:
                        if self.input_text:
                            _clipboard_set(self.input_text)
                    elif event.key == pygame.K_a and mods & pygame.KMOD_CTRL:
                        self.input_text = ""
                        cursor_tick = 0

            # ── Smooth transitions ───────────────────────────────────
            with self._snapshot_lock:
                current_app_state = self.app_state
                current_state = self.state
                current_response = self.last_response
                current_status_text = self.status_text
                current_input_enabled = self.input_enabled
                current_voice_trigger_enabled = self.voice_trigger_enabled
                current_audio_meter_visible = self.audio_meter_visible
                current_error_message = self.error_message
                current_busy = self.busy
                current_audio_level = self.audio_level

            cfg = STATES[current_state]
            state_meta = STATE_META.get(current_app_state, STATE_META[AppState.IDLE])
            accent_color = state_meta["accent"]
            self.audio_level_smooth = lerp(self.audio_level_smooth, current_audio_level, 0.22)
            for i in range(3):
                self.cur_color[i] = lerp(self.cur_color[i], cfg["color"][i], 0.04)
            self.cur_speed = lerp(self.cur_speed, cfg["speed"], 0.03)
            self.cur_pulse = lerp(self.cur_pulse, cfg["pulse"], 0.03)
            self.cur_glow  = lerp(self.cur_glow,  cfg["glow"],  0.03)

            color     = tuple(int(c) for c in self.cur_color)
            dim_color = tuple(max(0, int(c * 0.35)) for c in color)

            screen.fill(BG)

            # ── Background glow ──────────────────────────────────────
            glow_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for radius in range(160, 0, -8):
                alpha = int(4 * self.cur_glow * (1 - radius / 160))
                pygame.draw.circle(glow_surf, (*color, alpha), (CX, CY), radius)
            screen.blit(glow_surf, (0, 0))

            # ── 3D rotation ──────────────────────────────────────────
            rot_y = self.t * self.cur_speed * 0.3
            rot_x = math.sin(self.t * self.cur_speed * 0.15) * 0.25
            pulse = 1 + self.cur_pulse * math.sin(self.t * self.cur_speed * 2.5)

            projected = []
            for n in self.nodes:
                n["ox"] += n["vx"] * (1 + self.cur_speed * 0.2)
                n["oy"] += n["vy"] * (1 + self.cur_speed * 0.2)
                if abs(n["ox"]) > 12: n["vx"] *= -1
                if abs(n["oy"]) > 12: n["vy"] *= -1

                nx = n["bx"] - CX + n["ox"]
                ny = n["by"] - CY + n["oy"]
                nz = n["bz"]

                x1 =  nx * math.cos(rot_y) + nz * math.sin(rot_y)
                z1 = -nx * math.sin(rot_y) + nz * math.cos(rot_y)
                y2 =  ny * math.cos(rot_x) - z1 * math.sin(rot_x)
                z2 =  ny * math.sin(rot_x) + z1 * math.cos(rot_x)

                fov   = 280
                depth = fov / (fov + z2)
                px    = int(CX + x1 * depth * pulse)
                py    = int(CY + y2 * depth * pulse)
                alpha = 0.3 + 0.7 * ((z2 + 130) / 260)

                projected.append({
                    "x": px, "y": py, "z": z2,
                    "alpha": clamp(alpha, 0, 1),
                    "size": n["size"] * depth,
                })

            projected.sort(key=lambda p: p["z"])

            # ── Edges ────────────────────────────────────────────────
            edge_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for i in range(len(projected)):
                for j in range(i + 1, len(projected)):
                    a, b = projected[i], projected[j]
                    dx, dy = a["x"] - b["x"], a["y"] - b["y"]
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist > 90: continue
                    if random.random() > cfg["edge_prob"] * 2: continue
                    ea = (1 - dist / 90) * 0.25 * min(a["alpha"], b["alpha"]) * self.cur_glow
                    ai = clamp(int(ea * 255), 0, 255)
                    if ai < 2: continue
                    pygame.draw.line(edge_surf, (*color, ai), (a["x"], a["y"]), (b["x"], b["y"]), 1)
                    if current_state == "thinking" and random.random() < 0.003:
                        prog = (self.t * 3) % 1
                        fx = int(lerp(a["x"], b["x"], prog))
                        fy = int(lerp(a["y"], b["y"], prog))
                        pygame.draw.circle(edge_surf, (*color, 220), (fx, fy), 2)
            screen.blit(edge_surf, (0, 0))

            # ── Nodes ────────────────────────────────────────────────
            node_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for p in projected:
                na     = clamp(p["alpha"] * self.cur_glow, 0, 1)
                firing = current_state != "idle" and random.random() < 0.008
                if firing:
                    for gr in range(12, 0, -2):
                        pygame.draw.circle(node_surf, (*color, int(80 * (1 - gr / 12))), (p["x"], p["y"]), gr)
                r = max(1, int(p["size"] * (2.0 if firing else 1.0)))
                a = clamp(int(na * (1.5 if firing else 1.0) * 255), 0, 255)
                pygame.draw.circle(node_surf, (*color, a), (p["x"], p["y"]), r)
            screen.blit(node_surf, (0, 0))

            # ── Core ─────────────────────────────────────────────────
            core_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            core_size = 18 + 6 * math.sin(self.t * self.cur_speed * 3)
            for r in range(int(core_size * 2), 0, -1):
                ratio = r / (core_size * 2)
                a = int(230 * (1 - ratio / 0.3)) if ratio < 0.3 else int(100 * (1 - (ratio - 0.3) / 0.7))
                pygame.draw.circle(core_surf, (*color, clamp(a, 0, 255)), (CX, CY), r)
            pygame.draw.circle(core_surf, (*color, 240), (CX, CY), max(1, int(core_size * 0.4)))
            screen.blit(core_surf, (0, 0))

            # ── Rings ────────────────────────────────────────────────
            ring_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            outer_r = int(118 * pulse)
            pygame.draw.circle(ring_surf, (*color, clamp(int(0.07 * self.cur_glow * 255), 0, 255)), (CX, CY), outer_r, 1)
            dash_r = int(outer_r * 1.08)
            dash_a = clamp(int(0.12 * self.cur_glow * 255), 0, 255)
            offset = -self.t * 1.5 * self.cur_speed
            for d in range(18):
                s_a = offset + d * (math.pi * 2 / 18)
                e_a = s_a + math.pi / 18 * 0.45
                rect = pygame.Rect(CX - dash_r, CY - dash_r, dash_r * 2, dash_r * 2)
                try:
                    pygame.draw.arc(ring_surf, (*color, dash_a), rect, s_a, e_a, 1)
                except Exception:
                    pass
            uptime = time.time() - self.uptime_start
            for i, base_r in enumerate([170, 200, 230]):
                phase = (uptime * 0.33 + i * 0.33) % 1.0
                rpa   = clamp(int(math.sin(phase * math.pi) * 30), 0, 255)
                pygame.draw.circle(ring_surf, (*color, rpa), (CX, CY), int(base_r * (0.95 + 0.05 * phase)), 1)
            screen.blit(ring_surf, (0, 0))

            # ── Top status ───────────────────────────────────────────
            pill_gap = 10
            status_pad_x = 16
            status_pad_y = 8
            state_label = state_meta["label"]
            state_surface = font_micro.render(state_label, True, accent_color)
            state_w = state_surface.get_width() + status_pad_x * 2 + 16
            state_h = 28
            state_x = WIDTH // 2 - state_w // 2
            state_y = 18

            status_surf = pygame.Surface((state_w, state_h), pygame.SRCALPHA)
            pygame.draw.rect(status_surf, (*accent_color, 30), (0, 0, state_w, state_h), border_radius=14)
            pygame.draw.rect(status_surf, (*accent_color, 120), (0, 0, state_w, state_h), 1, border_radius=14)
            dot_alpha = 220 if current_busy else 150
            pygame.draw.circle(status_surf, (*accent_color, dot_alpha), (14, state_h // 2), 4)
            status_surf.blit(state_surface, (28, state_h // 2 - state_surface.get_height() // 2))
            screen.blit(status_surf, (state_x, state_y))

            subtitle = font_micro.render(current_status_text, True, (210, 232, 240))
            subtitle.set_alpha(155)
            screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, state_y + 35))

            def _draw_action_chip(center_x, y, label, enabled, accent, filled=False):
                txt = font_micro.render(label, True, accent if enabled else (140, 152, 160))
                w = txt.get_width() + 24
                h = 24
                x = center_x - w // 2
                chip = pygame.Surface((w, h), pygame.SRCALPHA)
                fill_alpha = 42 if enabled and filled else (18 if enabled else 6)
                border_alpha = 115 if enabled else 42
                pygame.draw.rect(chip, (*accent, fill_alpha), (0, 0, w, h), border_radius=12)
                pygame.draw.rect(chip, (*accent, border_alpha), (0, 0, w, h), 1, border_radius=12)
                chip.blit(txt, (w // 2 - txt.get_width() // 2, h // 2 - txt.get_height() // 2))
                screen.blit(chip, (x, y))

            chip_y = 66
            _draw_action_chip(
                WIDTH // 2 - 76,
                chip_y,
                "F8 pronto" if current_voice_trigger_enabled else "F8 indisponivel",
                current_voice_trigger_enabled,
                (112, 226, 255),
                filled=current_voice_trigger_enabled,
            )
            _draw_action_chip(
                WIDTH // 2 + 76,
                chip_y,
                "Enviar texto" if current_input_enabled else "Texto bloqueado",
                current_input_enabled,
                (106, 235, 214),
                filled=current_input_enabled,
            )

            hint = font_micro.render(state_meta["hint"], True, dim_color)
            hint.set_alpha(105)
            screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 96))

            if current_busy:
                dots_w = 40
                dots_y = 122
                phase = self.t * 4.0
                dots_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                for i in range(3):
                    alpha = int(90 + 120 * max(0.0, math.sin(phase - i * 0.45)))
                    pygame.draw.circle(
                        dots_surf,
                        (*accent_color, clamp(alpha, 0, 255)),
                        (WIDTH // 2 - dots_w // 2 + i * 18, dots_y),
                        3,
                    )
                screen.blit(dots_surf, (0, 0))

            # ── Title ────────────────────────────────────────────────
            name = font_title.render("ARIS", True, color)
            screen.blit(name, (WIDTH // 2 - name.get_width() // 2, HEIGHT - 310))

            # ── Response text ────────────────────────────────────────
            if current_response:
                pad_x  = 80
                pad_i  = 18
                pad_v  = 10
                line_h = 17

                title_bottom = (HEIGHT - 310) + 63
                sep_top      = box_y - 18
                available    = sep_top - title_bottom - 16
                max_ln       = max(1, (available - pad_v * 2) // line_h)

                wrap_w  = WIDTH - pad_x * 2 - pad_i * 2
                lines   = self._wrap_text(current_response, font_resp, wrap_w)
                shown   = lines[:max_ln]
                truncado = len(lines) > max_ln

                blk_w  = WIDTH - pad_x * 2
                blk_h  = len(shown) * line_h + pad_v * 2
                blk_y  = sep_top - blk_h - 8
                blk_x  = pad_x
                resp_rect = pygame.Rect(blk_x, blk_y, blk_w, blk_h)

                hover_resp = resp_rect.collidepoint(mouse_pos)
                if current_app_state == AppState.SPEAKING:
                    border_col = (*accent_color, 135 if hover_resp else 105)
                elif current_app_state == AppState.ERROR:
                    border_col = (255, 110, 110, 120 if hover_resp else 90)
                else:
                    border_col = (*color, 90) if hover_resp else (*color, 45)
                blk_surf = pygame.Surface((blk_w, blk_h), pygame.SRCALPHA)
                response_fill = (0, 8, 16, 215 if current_app_state == AppState.SPEAKING else 200)
                pygame.draw.rect(blk_surf, response_fill, (0, 0, blk_w, blk_h), border_radius=10)
                pygame.draw.rect(blk_surf, border_col,       (0, 0, blk_w, blk_h), 1, border_radius=10)
                screen.blit(blk_surf, (blk_x, blk_y))

                ry = blk_y + pad_v
                for i, line in enumerate(shown):
                    txt = (line + "  …") if (truncado and i == len(shown) - 1) else line
                    rs  = font_resp.render(txt, True, (235, 250, 255))
                    screen.blit(rs, (blk_x + pad_i, ry))
                    ry += line_h
            else:
                resp_rect = None

            # ── Separator ────────────────────────────────────────────
            sep_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.line(sep_surf, (*color, 25), (box_x, box_y - 18), (box_x + box_w, box_y - 18), 1)
            screen.blit(sep_surf, (0, 0))

            # ── Input box ────────────────────────────────────────────
            has_text = bool(self.input_text)
            focused  = over_input or over_btn

            border_a = 220 if (focused and current_input_enabled) else (95 if current_input_enabled else 38)
            bg_a     = 36  if (focused and current_input_enabled) else (16 if current_input_enabled else 6)
            ib_surf  = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
            pygame.draw.rect(ib_surf, (*color, bg_a),     (0, 0, box_w, box_h), border_radius=box_r)
            pygame.draw.rect(ib_surf, (*color, border_a), (0, 0, box_w, box_h), 1, border_radius=box_r)
            if not current_input_enabled:
                pygame.draw.rect(ib_surf, (255, 255, 255, 6), (0, 0, box_w, box_h), border_radius=box_r)
            screen.blit(ib_surf, (box_x, box_y))

            # Cursor blink
            cursor_tick += 1
            show_cursor  = (cursor_tick // 28) % 2 == 0
            text_y       = box_y + box_h // 2
            text_area_w  = box_w - btn_size - 28

            input_color = (225, 248, 255) if current_input_enabled else (130, 150, 160)
            if has_text:
                rendered = font_input.render(self.input_text, True, input_color)
                screen.blit(rendered, (box_x + 16, text_y - rendered.get_height() // 2))
                if show_cursor and current_input_enabled:
                    cx = box_x + 16 + min(rendered.get_width(), text_area_w) + 2
                    cs = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                    pygame.draw.line(cs, (*color, 210), (cx, text_y - 7), (cx, text_y + 7), 1)
                    screen.blit(cs, (0, 0))
            else:
                ph = font_input.render(
                    "mensagem..." if current_input_enabled else "aguarde o estado idle...",
                    True,
                    dim_color,
                )
                ph.set_alpha(110 if current_input_enabled else 85)
                screen.blit(ph, (box_x + 16, text_y - ph.get_height() // 2))
                if show_cursor and current_input_enabled:
                    cs = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                    pygame.draw.line(cs, (*color, 140), (box_x + 16, text_y - 7), (box_x + 16, text_y + 7), 1)
                    screen.blit(cs, (0, 0))

            # ── Send button ───────────────────────────────────────────
            btn_ready = has_text and current_input_enabled
            btn_a    = 255 if (btn_ready and over_btn) else (190 if btn_ready else 50)
            btn_fill = 220 if (btn_ready and over_btn) else (42 if btn_ready else 0)
            bs       = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            # circle background (filled when hovering with text)
            if btn_ready:
                pygame.draw.circle(bs, (*color, btn_fill), (btn_cx, btn_cy), btn_size // 2)
            pygame.draw.circle(bs, (*color, btn_a), (btn_cx, btn_cy), btn_size // 2, 1)
            # upward arrow (↑): shaft + head
            arr_color = (2, 6, 10) if (btn_ready and over_btn) else (*color,)
            arr_alpha = btn_a
            arr_s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            ax, ay = btn_cx, btn_cy
            # arrowhead (triangle)
            tip   = (ax,      ay - 8)
            lft   = (ax - 5,  ay - 2)
            rgt   = (ax + 5,  ay - 2)
            pygame.draw.polygon(arr_s, (*arr_color, arr_alpha), [tip, lft, rgt])
            # shaft
            pygame.draw.line(arr_s, (*arr_color, arr_alpha), (ax, ay - 2), (ax, ay + 6), 2)
            screen.blit(bs,    (0, 0))
            screen.blit(arr_s, (0, 0))

            # ── Indicador de microfone real ──────────────────────────
            if current_audio_meter_visible:
                meter_w, meter_h = 132, 18
                meter_x, meter_y = WIDTH // 2 - meter_w // 2, 136
                meter_level = clamp(self.audio_level_smooth, 0, 1)
                meter_surf = pygame.Surface((meter_w, meter_h), pygame.SRCALPHA)
                pygame.draw.rect(meter_surf, (18, 24, 32, 170), (0, 0, meter_w, meter_h), border_radius=9)
                pygame.draw.rect(meter_surf, (*color, 70), (0, 0, meter_w, meter_h), 1, border_radius=9)
                fill_w = max(6, int((meter_w - 4) * meter_level)) if meter_level > 0.01 else 0
                if fill_w:
                    meter_color = (255, 170, 60) if meter_level < 0.75 else (255, 110, 60)
                    pygame.draw.rect(meter_surf, (*meter_color, 220), (2, 2, fill_w, meter_h - 4), border_radius=7)
                mic_label = font_micro.render("MIC", True, (255, 214, 170))
                lvl_label = font_micro.render(f"{int(meter_level * 100):02d}", True, (255, 214, 170))
                screen.blit(meter_surf, (meter_x, meter_y))
                screen.blit(mic_label, (meter_x - 28, meter_y + 3))
                screen.blit(lvl_label, (meter_x + meter_w + 8, meter_y + 3))

            if current_error_message:
                err = font_micro.render(current_error_message, True, (255, 150, 150))
                err_w = err.get_width() + 26
                err_h = 26
                err_x = WIDTH // 2 - err_w // 2
                err_y = 134 if not current_audio_meter_visible else 164
                err_surf = pygame.Surface((err_w, err_h), pygame.SRCALPHA)
                pygame.draw.rect(err_surf, (90, 10, 16, 220), (0, 0, err_w, err_h), border_radius=13)
                pygame.draw.rect(err_surf, (255, 110, 110, 155), (0, 0, err_w, err_h), 1, border_radius=13)
                err_surf.blit(err, (13, err_h // 2 - err.get_height() // 2))
                screen.blit(err_surf, (err_x, err_y))

            footer_hint = font_micro.render(
                "ENTER envia texto" if current_input_enabled else "Novo texto disponivel apenas em idle",
                True,
                (180, 220, 235) if current_input_enabled else (134, 148, 156),
            )
            footer_hint.set_alpha(110 if current_input_enabled else 75)
            screen.blit(footer_hint, (box_x, box_y - 40))

            # ── Menu de contexto (clique direito) ─────────────────────
            if ctx["visible"] and ctx["items"]:
                n_items = len(ctx["items"])
                mh = n_items * CTX_ITEM_H + CTX_PAD * 2
                m_surf = pygame.Surface((CTX_W, mh), pygame.SRCALPHA)
                pygame.draw.rect(m_surf, (8, 16, 26, 245), (0, 0, CTX_W, mh), border_radius=CTX_R)
                pygame.draw.rect(m_surf, (*color, 120),    (0, 0, CTX_W, mh), 1, border_radius=CTX_R)
                for i, (label, _) in enumerate(ctx["items"]):
                    iy     = CTX_PAD + i * CTX_ITEM_H
                    ir     = pygame.Rect(ctx["x"], ctx["y"] + iy, CTX_W, CTX_ITEM_H)
                    if ir.collidepoint(mouse_pos):
                        pygame.draw.rect(m_surf, (*color, 35), (3, iy + 2, CTX_W - 6, CTX_ITEM_H - 4), border_radius=5)
                    lbl_s = font_input.render(label, True, (215, 240, 255))
                    m_surf.blit(lbl_s, (14, iy + (CTX_ITEM_H - lbl_s.get_height()) // 2))
                    if i < n_items - 1:
                        pygame.draw.line(m_surf, (*color, 25), (8, iy + CTX_ITEM_H), (CTX_W - 8, iy + CTX_ITEM_H))
                screen.blit(m_surf, (ctx["x"], ctx["y"]))

            pygame.display.flip()
            self.t += 1.0 / FPS
            clock.tick(FPS)

        pygame.quit()


if __name__ == "__main__":
    def handle_input(text):
        print(f"[Você]: {text}")
    orb = ARISOrb(on_input=handle_input)
    orb.run_blocking()
