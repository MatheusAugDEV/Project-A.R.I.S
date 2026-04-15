from __future__ import annotations

import math
import random
import subprocess
import threading
import time
from dataclasses import dataclass

import pygame

from src.aris.app.state_machine import AppState
from src.aris.app.ui_state import UIStateSnapshot

DEFAULT_WIDTH = 900
DEFAULT_HEIGHT = 960
MIN_WIDTH = 720
MIN_HEIGHT = 720
FPS = 60
BG = (2, 6, 10)

STATES = {
    "idle": {"speed": 0.4, "pulse": 0.03, "node_count": 60, "edge_prob": 0.18, "color": (0, 200, 220), "glow": 0.6, "label": "standby"},
    "listening": {"speed": 1.2, "pulse": 0.12, "node_count": 80, "edge_prob": 0.22, "color": (0, 229, 255), "glow": 1.0, "label": "listening"},
    "thinking": {"speed": 2.5, "pulse": 0.07, "node_count": 100, "edge_prob": 0.30, "color": (0, 160, 255), "glow": 1.2, "label": "processing"},
    "speaking": {"speed": 0.9, "pulse": 0.10, "node_count": 70, "edge_prob": 0.20, "color": (0, 220, 200), "glow": 0.9, "label": "responding"},
}

STATE_META = {
    AppState.BOOTING: {"label": "BOOTING", "accent": (255, 184, 82), "hint": "Inicializando modulos e preparando a sessao"},
    AppState.IDLE: {"label": "PRONTO", "accent": (90, 232, 235), "hint": "Texto e F8 disponiveis quando o runtime estiver pronto"},
    AppState.LISTENING: {"label": "ESCUTA ATIVA", "accent": (74, 240, 255), "hint": "Fale agora. Pressione F8 novamente para cancelar"},
    AppState.PROCESSING: {"label": "ANALISANDO", "accent": (80, 174, 255), "hint": "Interpretando comando e preparando resposta"},
    AppState.SPEAKING: {"label": "RESPONDENDO", "accent": (74, 225, 196), "hint": "ARIS esta falando"},
    AppState.ERROR: {"label": "ERRO", "accent": (255, 104, 104), "hint": "Falha recuperavel no runtime atual"},
    AppState.SHUTTING_DOWN: {"label": "ENCERRANDO", "accent": (255, 176, 92), "hint": "Finalizando sessao"},
}

CTX_W = 200
CTX_ITEM_H = 34
CTX_PAD = 5
CTX_R = 8
INPUT_CHAR_LIMIT = 120


def lerp(a, b, k):
    return a + (b - a) * k


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


@dataclass(frozen=True)
class FontSet:
    micro: pygame.font.Font
    title: pygame.font.Font
    input: pygame.font.Font
    response: pygame.font.Font


@dataclass(frozen=True)
class LayoutMetrics:
    width: int
    height: int
    cx: int
    cy: int
    box_rect: pygame.Rect
    input_rect: pygame.Rect
    button_rect: pygame.Rect
    box_radius: int
    title_y: int
    response_x: int
    response_top: int
    response_bottom: int
    response_width: int
    response_wrap_width: int
    response_pad_x: int
    response_pad_y: int
    response_line_height: int
    chip_y: int
    hint_y: int
    meter_y: int
    footer_y: int


class ARISOrb:
    def __init__(self, on_input=None):
        self._snapshot_lock = threading.RLock()
        self.app_state = AppState.IDLE
        self.state = "idle"
        self.running = False
        self._thread = None
        self.t = 0.0
        self.nodes = []
        self.cur_color = list(STATES["idle"]["color"])
        self.cur_speed = STATES["idle"]["speed"]
        self.cur_pulse = STATES["idle"]["pulse"]
        self.cur_glow = STATES["idle"]["glow"]
        self.uptime_start = time.time()
        self.on_input = on_input
        self.on_voice = None
        self.input_text = ""
        self.last_response = ""
        self._input_active = True
        self.audio_level = 0.0
        self.audio_level_smooth = 0.0
        self.status_text = "Aguardando comando"
        self.input_enabled = True
        self.voice_trigger_enabled = True
        self.audio_meter_visible = False
        self.error_message = None
        self.busy = False
        self.response_scroll = 0
        self._build_nodes("idle")

    def apply_snapshot(self, snapshot: UIStateSnapshot):
        with self._snapshot_lock:
            previous_response = self.last_response
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
            if previous_response != self.last_response:
                self.response_scroll = 0
            self._build_nodes(snapshot.visual_state)

    def set_state(self, state: str):
        if state in STATES:
            with self._snapshot_lock:
                self.state = state
                self._build_nodes(state)

    def set_response(self, text: str):
        with self._snapshot_lock:
            if self.last_response != text:
                self.response_scroll = 0
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

    def _build_nodes(self, state: str):
        count = STATES[state]["node_count"]
        self.nodes = []
        for _ in range(count):
            theta = random.uniform(0, math.pi * 2)
            phi = math.acos(2 * random.random() - 1)
            r = random.uniform(70, 115)
            self.nodes.append(
                {
                    "x": r * math.sin(phi) * math.cos(theta),
                    "y": r * math.sin(phi) * math.sin(theta),
                    "z": r * math.cos(phi),
                    "ox": random.uniform(-4, 4),
                    "oy": random.uniform(-4, 4),
                    "vx": random.uniform(-0.3, 0.3),
                    "vy": random.uniform(-0.3, 0.3),
                    "size": random.uniform(0.8, 2.6),
                }
            )

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
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
        return lines or [""]

    def _clip_tail_text(self, text: str, font: pygame.font.Font, max_width: int) -> str:
        if font.size(text)[0] <= max_width:
            return text
        clipped = text
        prefix = "…"
        while clipped and font.size(prefix + clipped)[0] > max_width:
            clipped = clipped[1:]
        return prefix + clipped if clipped else prefix

    def _create_fonts(self) -> FontSet:
        return FontSet(
            micro=pygame.font.SysFont("monospace", 11),
            title=pygame.font.SysFont("monospace", 52),
            input=pygame.font.SysFont("monospace", 15),
            response=pygame.font.SysFont("monospace", 13),
        )

    def _set_display_mode(self, size: tuple[int, int], *, fullscreen: bool) -> pygame.Surface:
        if fullscreen:
            return pygame.display.set_mode((0, 0), pygame.SCALED | pygame.FULLSCREEN)
        width = max(MIN_WIDTH, int(size[0]))
        height = max(MIN_HEIGHT, int(size[1]))
        return pygame.display.set_mode((width, height), pygame.SCALED | pygame.RESIZABLE)

    def _compute_layout(self, width: int, height: int, fonts: FontSet) -> LayoutMetrics:
        cx = width // 2
        cy = clamp(int(height * 0.43), 280, max(320, height - 360))

        box_pad = clamp(width // 12, 40, 72)
        box_w = max(420, width - box_pad * 2)
        box_h = 48
        box_y = height - 86
        box_x = (width - box_w) // 2
        box_radius = box_h // 2

        btn_size = 30
        btn_cx = box_x + box_w - btn_size // 2 - 9
        btn_cy = box_y + box_h // 2
        button_rect = pygame.Rect(btn_cx - btn_size // 2, btn_cy - btn_size // 2, btn_size, btn_size)
        input_rect = pygame.Rect(box_x, box_y, box_w - btn_size - 18, box_h)

        response_pad_x = clamp(width // 11, 40, 80)
        response_x = response_pad_x
        response_width = width - response_pad_x * 2
        response_wrap_width = response_width - 36
        response_pad_y = 12
        response_line_height = max(17, fonts.response.get_linesize() + 1)

        title_y = clamp(cy + 210, 180, box_y - 220)
        response_top = title_y + 72
        response_bottom = box_y - 26

        chip_y = 66
        hint_y = 96
        meter_y = 136
        footer_y = box_y - 40

        return LayoutMetrics(
            width=width,
            height=height,
            cx=cx,
            cy=cy,
            box_rect=pygame.Rect(box_x, box_y, box_w, box_h),
            input_rect=input_rect,
            button_rect=button_rect,
            box_radius=box_radius,
            title_y=title_y,
            response_x=response_x,
            response_top=response_top,
            response_bottom=response_bottom,
            response_width=response_width,
            response_wrap_width=response_wrap_width,
            response_pad_x=18,
            response_pad_y=response_pad_y,
            response_line_height=response_line_height,
            chip_y=chip_y,
            hint_y=hint_y,
            meter_y=meter_y,
            footer_y=footer_y,
        )

    def _clipboard_get(self) -> str:
        commands = [
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
            ["wl-paste", "--no-newline"],
        ]
        for cmd in commands:
            try:
                return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=1).decode("utf-8", errors="ignore")
            except Exception:
                continue
        return ""

    def _clipboard_set(self, text: str):
        commands = [
            (["xclip", "-selection", "clipboard"], text.encode("utf-8")),
            (["xsel", "--clipboard", "--input"], text.encode("utf-8")),
            (["wl-copy"], text.encode("utf-8")),
        ]
        for cmd, payload in commands:
            try:
                subprocess.run(cmd, input=payload, stderr=subprocess.DEVNULL, timeout=1, check=True)
                return
            except Exception:
                continue

    def _open_context_menu(self, ctx: dict, pos: tuple[int, int], items: list[tuple[str, object]], width: int, height: int):
        menu_height = len(items) * CTX_ITEM_H + CTX_PAD * 2
        ctx["visible"] = True
        ctx["x"] = min(pos[0], width - CTX_W - 4)
        ctx["y"] = min(pos[1], height - menu_height - 4)
        ctx["items"] = items

    def _ctx_item_rect(self, ctx: dict, index: int) -> pygame.Rect:
        return pygame.Rect(ctx["x"], ctx["y"] + CTX_PAD + index * CTX_ITEM_H, CTX_W, CTX_ITEM_H)

    def _send(self):
        text = self.input_text.strip()
        if text and self.on_input and self.input_enabled:
            threading.Thread(target=self.on_input, args=(text,), daemon=True).start()
            self.input_text = ""

    def _do_paste(self) -> bool:
        text = self._clipboard_get().replace("\n", " ").strip()
        if not text:
            return False
        available = INPUT_CHAR_LIMIT - len(self.input_text)
        self.input_text += text[:available]
        return True

    def _draw_background(self, screen: pygame.Surface, layout: LayoutMetrics, color: tuple[int, int, int], current_state: str):
        screen.fill(BG)

        glow_surf = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
        for radius in range(160, 0, -8):
            alpha = int(4 * self.cur_glow * (1 - radius / 160))
            pygame.draw.circle(glow_surf, (*color, alpha), (layout.cx, layout.cy), radius)
        screen.blit(glow_surf, (0, 0))

        rot_y = self.t * self.cur_speed * 0.3
        rot_x = math.sin(self.t * self.cur_speed * 0.15) * 0.25
        pulse = 1 + self.cur_pulse * math.sin(self.t * self.cur_speed * 2.5)

        projected = []
        for node in self.nodes:
            node["ox"] += node["vx"] * (1 + self.cur_speed * 0.2)
            node["oy"] += node["vy"] * (1 + self.cur_speed * 0.2)
            if abs(node["ox"]) > 12:
                node["vx"] *= -1
            if abs(node["oy"]) > 12:
                node["vy"] *= -1

            nx = node["x"] + node["ox"]
            ny = node["y"] + node["oy"]
            nz = node["z"]

            x1 = nx * math.cos(rot_y) + nz * math.sin(rot_y)
            z1 = -nx * math.sin(rot_y) + nz * math.cos(rot_y)
            y2 = ny * math.cos(rot_x) - z1 * math.sin(rot_x)
            z2 = ny * math.sin(rot_x) + z1 * math.cos(rot_x)

            fov = 280
            depth = fov / (fov + z2)
            px = int(layout.cx + x1 * depth * pulse)
            py = int(layout.cy + y2 * depth * pulse)
            alpha = 0.3 + 0.7 * ((z2 + 130) / 260)

            projected.append({"x": px, "y": py, "z": z2, "alpha": clamp(alpha, 0, 1), "size": node["size"] * depth})

        projected.sort(key=lambda item: item["z"])
        self._draw_edges(screen, layout, projected, color, current_state)
        self._draw_nodes(screen, layout, projected, color, current_state)
        self._draw_core(screen, layout, color, pulse)
        self._draw_rings(screen, layout, color, pulse)

    def _draw_edges(self, screen: pygame.Surface, layout: LayoutMetrics, projected: list[dict], color: tuple[int, int, int], current_state: str):
        edge_surf = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
        for i in range(len(projected)):
            for j in range(i + 1, len(projected)):
                a, b = projected[i], projected[j]
                dx, dy = a["x"] - b["x"], a["y"] - b["y"]
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > 90:
                    continue
                if random.random() > STATES[current_state]["edge_prob"] * 2:
                    continue
                edge_alpha = (1 - dist / 90) * 0.25 * min(a["alpha"], b["alpha"]) * self.cur_glow
                alpha_int = clamp(int(edge_alpha * 255), 0, 255)
                if alpha_int < 2:
                    continue
                pygame.draw.line(edge_surf, (*color, alpha_int), (a["x"], a["y"]), (b["x"], b["y"]), 1)
                if current_state == "thinking" and random.random() < 0.003:
                    progress = (self.t * 3) % 1
                    fx = int(lerp(a["x"], b["x"], progress))
                    fy = int(lerp(a["y"], b["y"], progress))
                    pygame.draw.circle(edge_surf, (*color, 220), (fx, fy), 2)
        screen.blit(edge_surf, (0, 0))

    def _draw_nodes(self, screen: pygame.Surface, layout: LayoutMetrics, projected: list[dict], color: tuple[int, int, int], current_state: str):
        node_surf = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
        for point in projected:
            normalized_alpha = clamp(point["alpha"] * self.cur_glow, 0, 1)
            firing = current_state != "idle" and random.random() < 0.008
            if firing:
                for glow_radius in range(12, 0, -2):
                    pygame.draw.circle(node_surf, (*color, int(80 * (1 - glow_radius / 12))), (point["x"], point["y"]), glow_radius)
            radius = max(1, int(point["size"] * (2.0 if firing else 1.0)))
            alpha = clamp(int(normalized_alpha * (1.5 if firing else 1.0) * 255), 0, 255)
            pygame.draw.circle(node_surf, (*color, alpha), (point["x"], point["y"]), radius)
        screen.blit(node_surf, (0, 0))

    def _draw_core(self, screen: pygame.Surface, layout: LayoutMetrics, color: tuple[int, int, int], pulse: float):
        core_surf = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
        core_size = 18 + 6 * math.sin(self.t * self.cur_speed * 3)
        for radius in range(int(core_size * 2), 0, -1):
            ratio = radius / (core_size * 2)
            alpha = int(230 * (1 - ratio / 0.3)) if ratio < 0.3 else int(100 * (1 - (ratio - 0.3) / 0.7))
            pygame.draw.circle(core_surf, (*color, clamp(alpha, 0, 255)), (layout.cx, layout.cy), radius)
        pygame.draw.circle(core_surf, (*color, 240), (layout.cx, layout.cy), max(1, int(core_size * 0.4)))
        screen.blit(core_surf, (0, 0))

    def _draw_rings(self, screen: pygame.Surface, layout: LayoutMetrics, color: tuple[int, int, int], pulse: float):
        ring_surf = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
        outer_r = int(118 * pulse)
        pygame.draw.circle(ring_surf, (*color, clamp(int(0.07 * self.cur_glow * 255), 0, 255)), (layout.cx, layout.cy), outer_r, 1)
        dash_r = int(outer_r * 1.08)
        dash_a = clamp(int(0.12 * self.cur_glow * 255), 0, 255)
        offset = -self.t * 1.5 * self.cur_speed
        for dash_index in range(18):
            start_angle = offset + dash_index * (math.pi * 2 / 18)
            end_angle = start_angle + math.pi / 18 * 0.45
            rect = pygame.Rect(layout.cx - dash_r, layout.cy - dash_r, dash_r * 2, dash_r * 2)
            try:
                pygame.draw.arc(ring_surf, (*color, dash_a), rect, start_angle, end_angle, 1)
            except Exception:
                pass
        uptime = time.time() - self.uptime_start
        for index, base_radius in enumerate([170, 200, 230]):
            phase = (uptime * 0.33 + index * 0.33) % 1.0
            ripple_alpha = clamp(int(math.sin(phase * math.pi) * 30), 0, 255)
            pygame.draw.circle(
                ring_surf,
                (*color, ripple_alpha),
                (layout.cx, layout.cy),
                int(base_radius * (0.95 + 0.05 * phase)),
                1,
            )
        screen.blit(ring_surf, (0, 0))

    def _draw_status_header(
        self,
        screen: pygame.Surface,
        layout: LayoutMetrics,
        fonts: FontSet,
        current_app_state: AppState,
        state_meta: dict,
        current_busy: bool,
        current_status_text: str,
        current_voice_trigger_enabled: bool,
        current_input_enabled: bool,
        accent_color: tuple[int, int, int],
        color: tuple[int, int, int],
        dim_color: tuple[int, int, int],
    ):
        status_pad_x = 16
        state_surface = fonts.micro.render(state_meta["label"], True, accent_color)
        state_w = state_surface.get_width() + status_pad_x * 2 + 16
        state_h = 28
        state_x = layout.width // 2 - state_w // 2
        state_y = 18

        status_surf = pygame.Surface((state_w, state_h), pygame.SRCALPHA)
        pygame.draw.rect(status_surf, (*accent_color, 30), (0, 0, state_w, state_h), border_radius=14)
        pygame.draw.rect(status_surf, (*accent_color, 120), (0, 0, state_w, state_h), 1, border_radius=14)
        dot_alpha = 220 if current_busy else 150
        pygame.draw.circle(status_surf, (*accent_color, dot_alpha), (14, state_h // 2), 4)
        status_surf.blit(state_surface, (28, state_h // 2 - state_surface.get_height() // 2))
        screen.blit(status_surf, (state_x, state_y))

        subtitle = fonts.micro.render(current_status_text, True, (210, 232, 240))
        subtitle.set_alpha(155)
        screen.blit(subtitle, (layout.width // 2 - subtitle.get_width() // 2, state_y + 35))

        if current_app_state == AppState.LISTENING and current_voice_trigger_enabled:
            f8_label = "F8 cancela"
            f8_filled = True
        elif current_voice_trigger_enabled:
            f8_label = "F8 inicia voz"
            f8_filled = True
        else:
            f8_label = "F8 indisponivel"
            f8_filled = False

        self._draw_action_chip(
            screen,
            fonts.micro,
            layout.width // 2 - 76,
            layout.chip_y,
            f8_label,
            current_voice_trigger_enabled,
            (112, 226, 255),
            filled=f8_filled,
        )
        self._draw_action_chip(
            screen,
            fonts.micro,
            layout.width // 2 + 76,
            layout.chip_y,
            "Enviar texto" if current_input_enabled else "Texto bloqueado",
            current_input_enabled,
            (106, 235, 214),
            filled=current_input_enabled,
        )

        hint = fonts.micro.render(state_meta["hint"], True, dim_color)
        hint.set_alpha(105)
        screen.blit(hint, (layout.width // 2 - hint.get_width() // 2, layout.hint_y))

        if current_busy:
            dots_w = 40
            dots_y = 122
            phase = self.t * 4.0
            dots_surf = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
            for index in range(3):
                alpha = int(90 + 120 * max(0.0, math.sin(phase - index * 0.45)))
                pygame.draw.circle(dots_surf, (*accent_color, clamp(alpha, 0, 255)), (layout.width // 2 - dots_w // 2 + index * 18, dots_y), 3)
            screen.blit(dots_surf, (0, 0))

        name = fonts.title.render("ARIS", True, color)
        screen.blit(name, (layout.width // 2 - name.get_width() // 2, layout.title_y))

    def _draw_action_chip(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        center_x: int,
        y: int,
        label: str,
        enabled: bool,
        accent: tuple[int, int, int],
        *,
        filled: bool = False,
    ):
        text = font.render(label, True, accent if enabled else (140, 152, 160))
        width = text.get_width() + 24
        height = 24
        x = center_x - width // 2
        chip = pygame.Surface((width, height), pygame.SRCALPHA)
        fill_alpha = 42 if enabled and filled else (18 if enabled else 6)
        border_alpha = 115 if enabled else 42
        pygame.draw.rect(chip, (*accent, fill_alpha), (0, 0, width, height), border_radius=12)
        pygame.draw.rect(chip, (*accent, border_alpha), (0, 0, width, height), 1, border_radius=12)
        chip.blit(text, (width // 2 - text.get_width() // 2, height // 2 - text.get_height() // 2))
        screen.blit(chip, (x, y))

    def _draw_response_panel(
        self,
        screen: pygame.Surface,
        layout: LayoutMetrics,
        fonts: FontSet,
        current_response: str,
        current_app_state: AppState,
        current_state: str,
        mouse_pos: tuple[int, int],
        accent_color: tuple[int, int, int],
        color: tuple[int, int, int],
    ) -> pygame.Rect | None:
        if not current_response:
            return None

        available = max(80, layout.response_bottom - layout.response_top)
        max_lines = max(2, (available - layout.response_pad_y * 2) // layout.response_line_height)
        lines = self._wrap_text(current_response, fonts.response, layout.response_wrap_width)
        max_scroll = max(0, len(lines) - max_lines)
        self.response_scroll = int(clamp(self.response_scroll, 0, max_scroll))
        shown = lines[self.response_scroll : self.response_scroll + max_lines]
        can_scroll_up = self.response_scroll > 0
        can_scroll_down = self.response_scroll < max_scroll

        block_height = len(shown) * layout.response_line_height + layout.response_pad_y * 2 + (18 if max_scroll else 0)
        block_height = min(block_height, available)
        block_y = layout.response_bottom - block_height
        response_rect = pygame.Rect(layout.response_x, block_y, layout.response_width, block_height)

        hover_response = response_rect.collidepoint(mouse_pos)
        if current_app_state == AppState.SPEAKING:
            border_col = (*accent_color, 135 if hover_response else 105)
        elif current_app_state == AppState.ERROR:
            border_col = (255, 110, 110, 120 if hover_response else 95)
        elif current_state == "listening":
            border_col = (112, 226, 255, 95 if hover_response else 75)
        else:
            border_col = (*color, 90) if hover_response else (*color, 45)

        block_surf = pygame.Surface((layout.response_width, block_height), pygame.SRCALPHA)
        response_fill = (0, 8, 16, 215 if current_app_state == AppState.SPEAKING else 200)
        pygame.draw.rect(block_surf, response_fill, (0, 0, layout.response_width, block_height), border_radius=10)
        pygame.draw.rect(block_surf, border_col, (0, 0, layout.response_width, block_height), 1, border_radius=10)
        screen.blit(block_surf, (layout.response_x, block_y))

        render_y = block_y + layout.response_pad_y
        for line in shown:
            rendered = fonts.response.render(line, True, (235, 250, 255))
            screen.blit(rendered, (layout.response_x + layout.response_pad_x, render_y))
            render_y += layout.response_line_height

        if can_scroll_up:
            top_hint = fonts.micro.render("...", True, (180, 220, 235))
            top_hint.set_alpha(120)
            screen.blit(top_hint, (layout.response_x + layout.response_width - 24, block_y + 6))

        if can_scroll_down:
            bottom_hint = fonts.micro.render("...", True, (180, 220, 235))
            bottom_hint.set_alpha(120)
            screen.blit(bottom_hint, (layout.response_x + layout.response_width - 24, block_y + block_height - 20))

        if max_scroll:
            scroll_hint = fonts.micro.render("Scroll para ler mais", True, (180, 220, 235))
            scroll_hint.set_alpha(110 if hover_response else 70)
            screen.blit(scroll_hint, (layout.response_x + layout.response_pad_x, block_y + block_height - 16))

        return response_rect

    def _draw_input_panel(
        self,
        screen: pygame.Surface,
        layout: LayoutMetrics,
        fonts: FontSet,
        mouse_pos: tuple[int, int],
        color: tuple[int, int, int],
        dim_color: tuple[int, int, int],
        current_input_enabled: bool,
    ):
        box_rect = layout.box_rect
        has_text = bool(self.input_text)
        focused = layout.input_rect.collidepoint(mouse_pos) or layout.button_rect.collidepoint(mouse_pos)

        border_alpha = 220 if (focused and current_input_enabled) else (95 if current_input_enabled else 38)
        bg_alpha = 36 if (focused and current_input_enabled) else (16 if current_input_enabled else 6)
        box_surf = pygame.Surface((box_rect.width, box_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(box_surf, (*color, bg_alpha), (0, 0, box_rect.width, box_rect.height), border_radius=layout.box_radius)
        pygame.draw.rect(box_surf, (*color, border_alpha), (0, 0, box_rect.width, box_rect.height), 1, border_radius=layout.box_radius)
        if not current_input_enabled:
            pygame.draw.rect(box_surf, (255, 255, 255, 6), (0, 0, box_rect.width, box_rect.height), border_radius=layout.box_radius)
        screen.blit(box_surf, box_rect.topleft)

        cursor_tick = int(self.t * FPS)
        show_cursor = (cursor_tick // 28) % 2 == 0
        text_y = box_rect.y + box_rect.height // 2
        text_area_w = box_rect.width - layout.button_rect.width - 28
        input_color = (225, 248, 255) if current_input_enabled else (130, 150, 160)

        if has_text:
            visible_text = self._clip_tail_text(self.input_text, fonts.input, text_area_w)
            rendered = fonts.input.render(visible_text, True, input_color)
            screen.blit(rendered, (box_rect.x + 16, text_y - rendered.get_height() // 2))
            if show_cursor and current_input_enabled:
                cursor_x = box_rect.x + 16 + min(rendered.get_width(), text_area_w) + 2
                cursor_surface = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
                pygame.draw.line(cursor_surface, (*color, 210), (cursor_x, text_y - 7), (cursor_x, text_y + 7), 1)
                screen.blit(cursor_surface, (0, 0))
        else:
            placeholder = fonts.input.render(
                "mensagem..." if current_input_enabled else "aguarde o estado idle...",
                True,
                dim_color,
            )
            placeholder.set_alpha(110 if current_input_enabled else 85)
            screen.blit(placeholder, (box_rect.x + 16, text_y - placeholder.get_height() // 2))
            if show_cursor and current_input_enabled:
                cursor_surface = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
                pygame.draw.line(cursor_surface, (*color, 140), (box_rect.x + 16, text_y - 7), (box_rect.x + 16, text_y + 7), 1)
                screen.blit(cursor_surface, (0, 0))

        self._draw_send_button(screen, layout, mouse_pos, color, has_text and current_input_enabled)

        separator = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
        pygame.draw.line(separator, (*color, 25), (box_rect.x, box_rect.y - 18), (box_rect.x + box_rect.width, box_rect.y - 18), 1)
        screen.blit(separator, (0, 0))

        footer = fonts.micro.render(
            "ENTER envia texto" if current_input_enabled else "Novo texto disponivel apenas em idle",
            True,
            (180, 220, 235) if current_input_enabled else (134, 148, 156),
        )
        footer.set_alpha(110 if current_input_enabled else 75)
        screen.blit(footer, (box_rect.x, layout.footer_y))

    def _draw_send_button(
        self,
        screen: pygame.Surface,
        layout: LayoutMetrics,
        mouse_pos: tuple[int, int],
        color: tuple[int, int, int],
        button_ready: bool,
    ):
        over_button = layout.button_rect.collidepoint(mouse_pos)
        button_alpha = 255 if (button_ready and over_button) else (190 if button_ready else 50)
        button_fill = 220 if (button_ready and over_button) else (42 if button_ready else 0)
        button_surface = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
        center = layout.button_rect.center
        if button_ready:
            pygame.draw.circle(button_surface, (*color, button_fill), center, layout.button_rect.width // 2)
        pygame.draw.circle(button_surface, (*color, button_alpha), center, layout.button_rect.width // 2, 1)

        arrow_color = (2, 6, 10) if (button_ready and over_button) else (*color,)
        arrow_surface = pygame.Surface((layout.width, layout.height), pygame.SRCALPHA)
        ax, ay = center
        tip = (ax, ay - 8)
        left = (ax - 5, ay - 2)
        right = (ax + 5, ay - 2)
        pygame.draw.polygon(arrow_surface, (*arrow_color, button_alpha), [tip, left, right])
        pygame.draw.line(arrow_surface, (*arrow_color, button_alpha), (ax, ay - 2), (ax, ay + 6), 2)

        screen.blit(button_surface, (0, 0))
        screen.blit(arrow_surface, (0, 0))

    def _draw_audio_meter(
        self,
        screen: pygame.Surface,
        layout: LayoutMetrics,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        visible: bool,
    ):
        if not visible:
            return
        meter_w, meter_h = 132, 18
        meter_x = layout.width // 2 - meter_w // 2
        meter_y = layout.meter_y
        meter_level = clamp(self.audio_level_smooth, 0, 1)
        meter_surface = pygame.Surface((meter_w, meter_h), pygame.SRCALPHA)
        pygame.draw.rect(meter_surface, (18, 24, 32, 170), (0, 0, meter_w, meter_h), border_radius=9)
        pygame.draw.rect(meter_surface, (*color, 70), (0, 0, meter_w, meter_h), 1, border_radius=9)
        fill_w = max(6, int((meter_w - 4) * meter_level)) if meter_level > 0.01 else 0
        if fill_w:
            meter_color = (255, 170, 60) if meter_level < 0.75 else (255, 110, 60)
            pygame.draw.rect(meter_surface, (*meter_color, 220), (2, 2, fill_w, meter_h - 4), border_radius=7)
        mic_label = font.render("MIC", True, (255, 214, 170))
        level_label = font.render(f"{int(meter_level * 100):02d}", True, (255, 214, 170))
        screen.blit(meter_surface, (meter_x, meter_y))
        screen.blit(mic_label, (meter_x - 28, meter_y + 3))
        screen.blit(level_label, (meter_x + meter_w + 8, meter_y + 3))

    def _draw_error_chip(self, screen: pygame.Surface, layout: LayoutMetrics, font: pygame.font.Font, current_audio_meter_visible: bool):
        if not self.error_message:
            return
        error = font.render(self.error_message, True, (255, 150, 150))
        error_w = error.get_width() + 26
        error_h = 26
        error_x = layout.width // 2 - error_w // 2
        error_y = 134 if not current_audio_meter_visible else 164
        error_surface = pygame.Surface((error_w, error_h), pygame.SRCALPHA)
        pygame.draw.rect(error_surface, (90, 10, 16, 220), (0, 0, error_w, error_h), border_radius=13)
        pygame.draw.rect(error_surface, (255, 110, 110, 155), (0, 0, error_w, error_h), 1, border_radius=13)
        error_surface.blit(error, (13, error_h // 2 - error.get_height() // 2))
        screen.blit(error_surface, (error_x, error_y))

    def _draw_context_menu(self, screen: pygame.Surface, ctx: dict, mouse_pos: tuple[int, int], font: pygame.font.Font, color: tuple[int, int, int]):
        if not ctx["visible"] or not ctx["items"]:
            return
        menu_height = len(ctx["items"]) * CTX_ITEM_H + CTX_PAD * 2
        menu_surface = pygame.Surface((CTX_W, menu_height), pygame.SRCALPHA)
        pygame.draw.rect(menu_surface, (8, 16, 26, 245), (0, 0, CTX_W, menu_height), border_radius=CTX_R)
        pygame.draw.rect(menu_surface, (*color, 120), (0, 0, CTX_W, menu_height), 1, border_radius=CTX_R)
        for index, (label, _) in enumerate(ctx["items"]):
            item_y = CTX_PAD + index * CTX_ITEM_H
            item_rect = self._ctx_item_rect(ctx, index)
            if item_rect.collidepoint(mouse_pos):
                pygame.draw.rect(menu_surface, (*color, 35), (3, item_y + 2, CTX_W - 6, CTX_ITEM_H - 4), border_radius=5)
            label_surface = font.render(label, True, (215, 240, 255))
            menu_surface.blit(label_surface, (14, item_y + (CTX_ITEM_H - label_surface.get_height()) // 2))
            if index < len(ctx["items"]) - 1:
                pygame.draw.line(menu_surface, (*color, 25), (8, item_y + CTX_ITEM_H), (CTX_W - 8, item_y + CTX_ITEM_H))
        screen.blit(menu_surface, (ctx["x"], ctx["y"]))

    def _run(self):
        pygame.mixer.pre_init(0, 0, 0, 0)
        pygame.init()
        pygame.mixer.quit()
        fullscreen = False
        windowed_size = (DEFAULT_WIDTH, DEFAULT_HEIGHT)
        screen = self._set_display_mode(windowed_size, fullscreen=fullscreen)
        pygame.display.set_caption("ARIS")
        clock = pygame.time.Clock()
        fonts = self._create_fonts()
        pygame.key.start_text_input()

        current_cursor = pygame.SYSTEM_CURSOR_ARROW
        ctx = {"visible": False, "x": 0, "y": 0, "items": []}
        response_rect = None

        while self.running:
            width, height = screen.get_size()
            layout = self._compute_layout(width, height, fonts)
            mouse_pos = pygame.mouse.get_pos()
            over_input = layout.input_rect.collidepoint(mouse_pos)
            over_button = layout.button_rect.collidepoint(mouse_pos)
            over_response = response_rect is not None and response_rect.collidepoint(mouse_pos)
            over_context = ctx["visible"] and any(self._ctx_item_rect(ctx, index).collidepoint(mouse_pos) for index in range(len(ctx["items"])))

            desired_cursor = pygame.SYSTEM_CURSOR_HAND if (over_button or over_context) else (pygame.SYSTEM_CURSOR_IBEAM if over_input else pygame.SYSTEM_CURSOR_ARROW)
            if desired_cursor != current_cursor:
                pygame.mouse.set_cursor(desired_cursor)
                current_cursor = desired_cursor

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.VIDEORESIZE and not fullscreen:
                    windowed_size = (max(MIN_WIDTH, event.w), max(MIN_HEIGHT, event.h))
                    screen = self._set_display_mode(windowed_size, fullscreen=False)

                elif event.type == pygame.MOUSEWHEEL:
                    if over_response:
                        self.response_scroll -= event.y

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    if over_response and self.last_response:
                        self._open_context_menu(ctx, event.pos, [("Copiar resposta", lambda: self._clipboard_set(self.last_response))], width, height)
                    elif over_input or over_button:
                        items = [("Colar", self._do_paste)]
                        if self.input_text:
                            items.append(("Copiar entrada", lambda: self._clipboard_set(self.input_text)))
                            items.append(("Limpar", lambda: setattr(self, "input_text", "")))
                        self._open_context_menu(ctx, event.pos, items, width, height)
                    else:
                        ctx["visible"] = False

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if ctx["visible"]:
                        for index, (_, fn) in enumerate(ctx["items"]):
                            if self._ctx_item_rect(ctx, index).collidepoint(mouse_pos):
                                fn()
                                break
                        ctx["visible"] = False
                    elif over_button:
                        self._send()

                elif event.type == pygame.TEXTINPUT:
                    if len(self.input_text) < INPUT_CHAR_LIMIT:
                        available = INPUT_CHAR_LIMIT - len(self.input_text)
                        self.input_text += event.text[:available]

                elif event.type == pygame.KEYDOWN:
                    mods = pygame.key.get_mods()
                    if event.key == pygame.K_ESCAPE:
                        if fullscreen:
                            fullscreen = False
                            screen = self._set_display_mode(windowed_size, fullscreen=False)
                        else:
                            self.running = False
                    elif event.key == pygame.K_F11:
                        if fullscreen:
                            fullscreen = False
                            screen = self._set_display_mode(windowed_size, fullscreen=False)
                        else:
                            windowed_size = screen.get_size()
                            fullscreen = True
                            screen = self._set_display_mode(windowed_size, fullscreen=True)
                    elif event.key == pygame.K_F8:
                        if self.on_voice:
                            threading.Thread(target=self.on_voice, daemon=True).start()
                    elif event.key == pygame.K_RETURN:
                        self._send()
                    elif event.key == pygame.K_BACKSPACE:
                        if mods & pygame.KMOD_CTRL:
                            parts = self.input_text.rstrip().rsplit(" ", 1)
                            self.input_text = parts[0] + " " if len(parts) > 1 else ""
                        else:
                            self.input_text = self.input_text[:-1]
                    elif event.key == pygame.K_v and mods & pygame.KMOD_CTRL:
                        self._do_paste()
                    elif event.key == pygame.K_c and mods & pygame.KMOD_CTRL:
                        if self.input_text:
                            self._clipboard_set(self.input_text)
                    elif event.key == pygame.K_a and mods & pygame.KMOD_CTRL:
                        self.input_text = ""

            with self._snapshot_lock:
                current_app_state = self.app_state
                current_state = self.state
                current_response = self.last_response
                current_status_text = self.status_text
                current_input_enabled = self.input_enabled
                current_voice_trigger_enabled = self.voice_trigger_enabled
                current_audio_meter_visible = self.audio_meter_visible
                current_busy = self.busy
                current_audio_level = self.audio_level

            cfg = STATES[current_state]
            state_meta = STATE_META.get(current_app_state, STATE_META[AppState.IDLE])
            accent_color = state_meta["accent"]
            self.audio_level_smooth = lerp(self.audio_level_smooth, current_audio_level, 0.22)
            for index in range(3):
                self.cur_color[index] = lerp(self.cur_color[index], cfg["color"][index], 0.04)
            self.cur_speed = lerp(self.cur_speed, cfg["speed"], 0.03)
            self.cur_pulse = lerp(self.cur_pulse, cfg["pulse"], 0.03)
            self.cur_glow = lerp(self.cur_glow, cfg["glow"], 0.03)

            color = tuple(int(c) for c in self.cur_color)
            dim_color = tuple(max(0, int(c * 0.35)) for c in color)

            self._draw_background(screen, layout, color, current_state)
            self._draw_status_header(
                screen,
                layout,
                fonts,
                current_app_state,
                state_meta,
                current_busy,
                current_status_text,
                current_voice_trigger_enabled,
                current_input_enabled,
                accent_color,
                color,
                dim_color,
            )
            response_rect = self._draw_response_panel(
                screen,
                layout,
                fonts,
                current_response,
                current_app_state,
                current_state,
                mouse_pos,
                accent_color,
                color,
            )
            self._draw_input_panel(screen, layout, fonts, mouse_pos, color, dim_color, current_input_enabled)
            self._draw_audio_meter(screen, layout, fonts.micro, color, current_audio_meter_visible)
            self._draw_error_chip(screen, layout, fonts.micro, current_audio_meter_visible)
            self._draw_context_menu(screen, ctx, mouse_pos, fonts.input, color)

            pygame.display.flip()
            self.t += 1.0 / FPS
            clock.tick(FPS)

        pygame.quit()


if __name__ == "__main__":
    def handle_input(text):
        print(f"[Você]: {text}")

    orb = ARISOrb(on_input=handle_input)
    orb.run_blocking()
