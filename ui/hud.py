"""
ui/hud.py — Main fullscreen Iron Man HUD for J.A.R.V.I.S. (PySide6)

Composites all UI elements using QPainter-based custom rendering at 30fps.
Features:
- Arc reactor with state-driven animations
- Voice waveform visualization
- Radar sweep with command blips
- System diagnostics panel (CPU, RAM, GPU, Battery, Disk, Network)
- Activity log panel
- Text input bar for typed commands
- Toast notification system
- Conversation display
- Floating holographic particles
- Keyboard shortcuts (F11 fullscreen, F10 mini mode, F9 always-on-top, ESC exit)

PySide6 Migration Notes:
- tkinter Canvas → QPainter (custom paintEvent)
- tk.after() → QTimer
- tk.mainloop() → QApplication.exec()
- All public API methods are preserved for backward compatibility
"""
import sys
import time
import math
import random
from collections import deque
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLineEdit, QPushButton,
    QHBoxLayout, QVBoxLayout, QFrame,
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontDatabase,
    QLinearGradient, QRadialGradient, QPainterPath, QKeyEvent,
    QMouseEvent, QPaintEvent, QResizeEvent,
)

from ui.colors import (
    BG, BG_PANEL, PRIMARY, PRIMARY_DIM, PRIMARY_DARK, SECONDARY,
    TEXT, TEXT_DIM, TEXT_BRIGHT, BORDER, BORDER_BRIGHT, GRID,
    ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED,
    REACTOR_CORE, REACTOR_RING, REACTOR_OUTER,
    WAVEFORM, WAVEFORM_DIM, RADAR, RADAR_DIM,
    hex_to_rgb, lerp_color, dim_color,
)

from core.logger import get_logger

log = get_logger("ui.hud")


def _qc(hex_color: str, alpha: int = 255) -> QColor:
    """Fast hex → QColor with optional alpha."""
    r, g, b = hex_to_rgb(hex_color)
    return QColor(r, g, b, alpha)


# ═══════════════════════════════════════════════════════════
# Central Canvas Widget (QPainter-based rendering)
# ═══════════════════════════════════════════════════════════

class HUDCanvas(QWidget):
    """Custom widget that renders the entire HUD via QPainter."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

        # ─── Animation State ─────────────────────────
        self.state = "idle"
        self.angle1 = 0.0
        self.angle2 = 0.0
        self.angle3 = 0.0
        self.pulse = 0.0
        self.radar_angle = 0.0

        # ─── Waveform Data ───────────────────────────
        self.waveform_levels = [0.0] * 32
        self.waveform_active = False

        # ─── System Stats ────────────────────────────
        self.stats = {}

        # ─── Command Log ─────────────────────────────
        self.command_log = []

        # ─── Radar Blips ─────────────────────────────
        self.radar_blips = []

        # ─── Notifications ───────────────────────────
        self.notifications: deque[dict] = deque(maxlen=5)

        # ─── Conversation ────────────────────────────
        self.conversation: deque[dict] = deque(maxlen=8)

        # ─── Particles ──────────────────────────────
        self.particles = []
        self._init_particles(35)

        # Fonts
        self._font_main = QFont("Consolas", 10)
        self._font_small = QFont("Consolas", 8)
        self._font_title = QFont("Consolas", 10, QFont.Bold)
        self._font_state = QFont("Consolas", 12, QFont.Bold)
        self._font_footer = QFont("Consolas", 7)

        # ─── Event Bus Connection ────────────────────
        self.current_stage = "idle"
        self.current_stage_label = "Ready"
        try:
            from core.event_bus import bus, Events
            bus.on(Events.STATE_CHANGED, self._on_bus_state_changed)
            bus.on(Events.COMMAND_STAGE, self._on_bus_command_stage)
            bus.on(Events.COMMAND_COMPLETED, self._on_bus_command_completed)
            bus.on(Events.NOTIFICATION, self._on_bus_notification)
            bus.on(Events.SYSTEM_STATS, self._on_bus_system_stats)
            bus.on(Events.MEMORY_UPDATED, self._on_bus_memory_updated)
        except Exception as e:
            log.warning("HUD Event Bus subscription failed: %s", e)

    def _on_bus_state_changed(self, event, state, prev_state, error_msg=""):
        self.state = state
        self.waveform_active = state in ("listening", "active_listening")
        status_map = {
            "idle": "SYSTEM ONLINE — STANDBY",
            "listening": "● ACTIVE LISTENING",
            "understanding": "⚡ UNDERSTANDING COMMAND",
            "thinking": "🧠 PROCESSING INTENT",
            "executing": "⚙ EXECUTING COMMAND",
            "speaking": "◆ RESPONDING",
            "monitoring": "○ MONITORING SYSTEMS",
            "error": "⚠ SYSTEM ERROR",
        }
        self._status_text = status_map.get(state, "SYSTEM ONLINE")
        self.update()

    def _on_bus_command_stage(self, event, stage, label):
        self.current_stage = stage
        self.current_stage_label = label
        self.update()

    def _on_bus_command_completed(self, event, command, response, duration_ms, success):
        # Format command log entry
        from datetime import datetime
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "command": command,
            "response": f"{response} ({duration_ms}ms)" if response else f"({duration_ms}ms)"
        }
        self.command_log.append(entry)
        if len(self.command_log) > 50:
            self.command_log.pop(0)
        self.current_stage = "idle"
        self.current_stage_label = "Ready"
        self.radar_blips.append({"angle": random.randint(0, 359), "time": time.time()})
        self.update()

    def _on_bus_notification(self, event, title, message, level="info"):
        self.notifications.append({
            "message": f"{title}: {message}",
            "color": {
                "info": PRIMARY,
                "success": ACCENT_GREEN,
                "warning": "#ff9000",
                "error": "#ff0040",
            }.get(level, PRIMARY),
            "time": time.time(),
            "duration": 5.0
        })
        self.update()

    def _on_bus_system_stats(self, event, stats):
        self.stats = stats
        self.update()

    def _on_bus_memory_updated(self, event, category, key):
        self.notifications.append({
            "message": f"Memory Updated: {category}/{key}",
            "color": ACCENT_GREEN,
            "time": time.time(),
            "duration": 4.0
        })
        self.update()

    def _init_particles(self, count: int):
        """Initialize floating holographic particles."""
        for _ in range(count):
            self.particles.append({
                "x": random.random(),
                "y": random.random(),
                "vx": (random.random() - 0.5) * 0.3,
                "vy": (random.random() - 0.5) * 0.3,
                "size": random.uniform(1, 3),
                "alpha": random.uniform(0.2, 0.7),
                "phase": random.random() * math.pi * 2,
            })

    def update_animation(self, dt: float):
        """Update all animation state. Called by timer."""
        # Arc reactor rotation speeds
        speed_table = {
            "idle":             (0.5, -0.3, 0.2, 2.0),
            "listening":        (3.0, -4.5, 6.0, 5.0),
            "understanding":    (6.0, -8.0, 10.0, 7.0),
            "thinking":         (8.0, -10.0, 12.0, 8.0),
            "executing":        (10.0, -5.0, 15.0, 10.0),
            "speaking":         (2.0, -3.0, 4.0, 4.0),
            "monitoring":       (0.2, -0.1, 0.1, 1.0),
            "error":            (15.0, -15.0, 20.0, 15.0),
        }
        s1, s2, s3, sp = speed_table.get(self.state, (0.5, -0.3, 0.2, 2.0))

        self.angle1 += s1 * dt * 60
        self.angle2 += s2 * dt * 60
        self.angle3 += s3 * dt * 60
        self.pulse += sp * dt
        if self.pulse > math.pi * 2:
            self.pulse -= math.pi * 2

        # Radar sweep
        self.radar_angle = (self.radar_angle + 45 * dt) % 360

        # Particles
        for p in self.particles:
            p["x"] += p["vx"] * dt * 0.02
            p["y"] += p["vy"] * dt * 0.02
            p["phase"] += dt * 2
            if p["x"] < 0 or p["x"] > 1:
                p["vx"] *= -1
            if p["y"] < 0 or p["y"] > 1:
                p["vy"] *= -1
            p["x"] = max(0, min(1, p["x"]))
            p["y"] = max(0, min(1, p["y"]))

        # Decay radar blips
        now = time.time()
        self.radar_blips = [b for b in self.radar_blips if now - b["time"] < 5.0]

        self.update()  # Trigger repaint

    def paintEvent(self, event: QPaintEvent):
        """Main paint method — renders the entire HUD."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        # Background
        painter.fillRect(0, 0, w, h, _qc(BG))

        # Grid
        self._draw_grid(painter, w, h)

        # Particles (background layer)
        self._draw_particles(painter, w, h)

        # Panels
        panel_w = int(w * 0.20)
        panel_h = h - 140
        self._draw_activity_panel(painter, 20, 110, panel_w, panel_h)
        self._draw_intelligence_panel(painter, w - panel_w - 20, 110, panel_w, panel_h)

        # Bottom panel strip
        self._draw_bottom_panel(painter, panel_w + 40, h - 145, w - (panel_w * 2) - 80, 80)

        # Top bar
        self._draw_top_bar(painter, w)

        # Arc reactor
        reactor_r = min(140, h // 5)
        self._draw_arc_reactor(painter, cx, cy - 40, reactor_r)

        # Waveform (just above bottom panel)
        self._draw_waveform(painter, cx, h - 170, min(500, w // 3))

        # Radar (bottom left corner of center area)
        self._draw_radar(painter, panel_w + 100, h - 230, 50)

        # Notifications
        self._draw_notifications(painter, w)

        # Conversation (positioned below state text and above waveform)
        self._draw_conversation(painter, cx, cy - 40 + reactor_r + 80)

        # Footer
        painter.setPen(_qc(TEXT_DIM))
        painter.setFont(self._font_footer)
        painter.drawText(
            QRectF(0, h - 25, w, 20), Qt.AlignCenter,
            "J.A.R.V.I.S. — Just A Rather Very Intelligent System  │  F11 Fullscreen  │  F10 Mini  │  F9 Pin  │  ESC Exit"
        )

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        """Emit clicked signal on canvas click."""
        self.clicked.emit()

    # ─── Grid ────────────────────────────────────────────

    def _draw_grid(self, p: QPainter, w: int, h: int):
        pen = QPen(_qc("#0a0f18"), 1)
        p.setPen(pen)
        spacing = 60
        for x in range(0, w, spacing):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, spacing):
            p.drawLine(0, y, w, y)

    # ─── Particles ───────────────────────────────────────

    def _draw_particles(self, p: QPainter, w: int, h: int):
        for pt in self.particles:
            x = pt["x"] * w
            y = pt["y"] * h
            alpha = int(pt["alpha"] * 255 * ((math.sin(pt["phase"]) + 1) / 2))
            alpha = max(10, min(200, alpha))
            p.setPen(Qt.NoPen)
            p.setBrush(_qc(PRIMARY, alpha))
            p.drawEllipse(QPointF(x, y), pt["size"], pt["size"])

    # ─── Top Bar ─────────────────────────────────────────

    def _draw_top_bar(self, p: QPainter, w: int):
        # Background
        p.fillRect(0, 0, w, 90, _qc(BG_PANEL, 200))
        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(0, 90, w, 90)

        # Title
        p.setPen(_qc(PRIMARY))
        title_font = QFont("Consolas", 16, QFont.Bold)
        p.setFont(title_font)
        p.drawText(QRectF(20, 10, 400, 30), Qt.AlignLeft | Qt.AlignVCenter, "J.A.R.V.I.S.")

        # Subtitle
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(QRectF(20, 38, 400, 20), Qt.AlignLeft, "Just A Rather Very Intelligent System")

        # Status
        p.setPen(_qc(PRIMARY))
        p.setFont(self._font_title)
        status = getattr(self, "_status_text", "SYSTEM ONLINE — STANDBY")
        p.drawText(QRectF(0, 60, w, 25), Qt.AlignCenter, status)

        # Clock
        from datetime import datetime
        clock = datetime.now().strftime("%H:%M:%S")
        p.setPen(_qc(TEXT))
        p.setFont(self._font_main)
        p.drawText(QRectF(w - 150, 15, 130, 25), Qt.AlignRight | Qt.AlignVCenter, clock)

        # Date
        date = datetime.now().strftime("%a %d %b %Y")
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(QRectF(w - 150, 38, 130, 20), Qt.AlignRight, date)

    # ─── Arc Reactor ─────────────────────────────────────

    def _draw_arc_reactor(self, p: QPainter, cx: int, cy: int, r: int):
        # Pulse calculation
        pulse_val = (math.sin(self.pulse) + 1) / 2

        # ─── Dynamic Ring & Core Colors ───
        if self.state == "listening":
            core_color = lerp_color(REACTOR_CORE, "#ffffff", pulse_val * 0.5)
            core_r = int(r * 0.22 + pulse_val * 8)
            ring_color = PRIMARY
        elif self.state == "understanding":
            core_color = lerp_color(REACTOR_CORE, "#ffffff", pulse_val * 0.6)
            core_r = int(r * 0.22 + pulse_val * 10)
            ring_color = SECONDARY
        elif self.state == "thinking":
            core_color = lerp_color("#ffaa00", "#ff6600", pulse_val * 0.7)
            core_r = int(r * 0.22 + pulse_val * 12)
            ring_color = "#ffaa00"
        elif self.state == "executing":
            core_color = lerp_color(ACCENT_GREEN, "#ffffff", pulse_val * 0.5)
            core_r = int(r * 0.24 + pulse_val * 6)
            ring_color = ACCENT_GREEN
        elif self.state == "speaking":
            # Wave-synchronized core sizing based on audio amplitude
            avg_level = sum(self.waveform_levels) / len(self.waveform_levels) if self.waveform_levels else 0.0
            core_color = lerp_color(REACTOR_CORE, "#e0ffff", pulse_val * 0.6)
            core_r = int(r * 0.22 + avg_level * 35)
            ring_color = PRIMARY
        elif self.state == "error":
            core_color = lerp_color(ACCENT_RED, "#ff8080", pulse_val * 0.6)
            core_r = int(r * 0.22 + pulse_val * 15)
            ring_color = ACCENT_RED
        elif self.state == "monitoring":
            core_color = lerp_color(PRIMARY_DARK, PRIMARY_DIM, pulse_val * 0.3)
            core_r = int(r * 0.18 + pulse_val * 2)
            ring_color = PRIMARY_DARK
        else:  # idle / standby
            core_color = lerp_color(REACTOR_CORE, PRIMARY, pulse_val * 0.3)
            core_r = int(r * 0.20 + pulse_val * 4)
            ring_color = REACTOR_RING

        # Determine structural ring colors based on state
        outer_dot_color = REACTOR_OUTER if self.state != "error" else ACCENT_RED
        mid_tick_color = PRIMARY_DIM if self.state != "error" else ACCENT_RED
        inner_seg_color = ring_color

        # Outer decorative ring
        self._draw_dot_ring(p, cx, cy, r + 20, 16, self.angle1, outer_dot_color)

        # Outer segmented ring
        self._draw_seg_ring(p, cx, cy, r, r + 10, ring_color, 12, self.angle1, gap=15)

        # Middle tick ring
        self._draw_tick_ring(p, cx, cy, r - 10, r - 2, mid_tick_color, 36, self.angle2)

        # Inner segmented ring
        self._draw_seg_ring(p, cx, cy, r - 30, r - 18, inner_seg_color, 8, self.angle3, gap=20)

        # Inner tick ring
        self._draw_tick_ring(p, cx, cy, r - 45, r - 35, mid_tick_color, 24, -self.angle3)

        # Outer glow halos
        for i in range(3):
            glow_r = core_r + (3 - i) * 8
            glow_color = dim_color(core_color, 0.15 + i * 0.05)
            p.setPen(Qt.NoPen)
            p.setBrush(_qc(glow_color, 60))
            p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # Core
        p.setPen(QPen(_qc(dim_color(core_color, 0.7)), 2))
        p.setBrush(_qc(core_color))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # Center dot
        dot_r = max(2, core_r // 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(cx, cy), dot_r, dot_r)

        # State text
        state_text = {
            "idle": "STANDBY",
            "listening": "● LISTENING",
            "understanding": "⚡ UNDERSTANDING",
            "thinking": "🧠 THINKING",
            "executing": "⚙ EXECUTING",
            "speaking": "◆ SPEAKING",
            "monitoring": "○ MONITORING",
            "error": "⚠ SYSTEM ERROR",
        }.get(self.state, "STANDBY")

        state_color = {
            "idle": PRIMARY_DIM,
            "listening": PRIMARY,
            "understanding": SECONDARY,
            "thinking": "#ffaa00",
            "executing": ACCENT_GREEN,
            "speaking": REACTOR_CORE,
            "monitoring": PRIMARY_DIM,
            "error": ACCENT_RED,
        }.get(self.state, PRIMARY_DIM)

        p.setPen(_qc(state_color))
        p.setFont(self._font_state)
        p.drawText(QRectF(cx - 150, cy + r + 30, 300, 25), Qt.AlignCenter, state_text)

        # Command stage label subtext
        stage_label = getattr(self, "current_stage_label", "")
        if stage_label and stage_label != "Ready" and self.state != "idle":
            p.setPen(_qc(TEXT_DIM))
            p.setFont(self._font_small)
            p.drawText(QRectF(cx - 200, cy + r + 55, 400, 20), Qt.AlignCenter, stage_label)

    def _draw_dot_ring(self, p, cx, cy, r, count, angle, color):
        p.setPen(Qt.NoPen)
        p.setBrush(_qc(color))
        for i in range(count):
            a = math.radians(angle + i * (360 / count))
            x = cx + r * math.cos(a)
            y = cy + r * math.sin(a)
            p.drawEllipse(QPointF(x, y), 2, 2)

    def _draw_seg_ring(self, p, cx, cy, r_inner, r_outer, color, num, angle, gap=10):
        pen = QPen(_qc(color), 3)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        seg = 360 / num - gap
        for i in range(num):
            start = int((angle + i * (360 / num)) * 16)
            span = int(seg * 16)
            rect = QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2)
            p.drawArc(rect, start, span)

    def _draw_tick_ring(self, p, cx, cy, r_inner, r_outer, color, count, angle):
        pen = QPen(_qc(color), 1)
        p.setPen(pen)
        for i in range(count):
            a = math.radians(angle + i * (360 / count))
            x1, y1 = cx + r_inner * math.cos(a), cy + r_inner * math.sin(a)
            x2, y2 = cx + r_outer * math.cos(a), cy + r_outer * math.sin(a)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # ─── Waveform ────────────────────────────────────────

    def _draw_waveform(self, p: QPainter, cx: int, cy: int, width: int):
        num_bars = len(self.waveform_levels)
        bar_w = max(2, width // (num_bars * 2))
        gap = 2
        total_w = num_bars * (bar_w + gap)
        start_x = cx - total_w // 2

        for i, level in enumerate(self.waveform_levels):
            x = start_x + i * (bar_w + gap)
            h = max(2, int(level * 200))
            if self.waveform_active and level > 0.01:
                color = _qc(WAVEFORM, 200)
            else:
                color = _qc(WAVEFORM_DIM, 100)
                h = max(2, h // 3)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRect(x, cy - h // 2, bar_w, h)

    # ─── Radar ───────────────────────────────────────────

    def _draw_radar(self, p: QPainter, cx: int, cy: int, r: int):
        # Background circle
        p.setPen(QPen(_qc(BORDER), 1))
        p.setBrush(_qc(RADAR_DIM, 80))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Concentric rings
        for ring_r in (r * 0.33, r * 0.66):
            p.setPen(QPen(_qc(BORDER), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # Crosshair
        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(cx - r, cy, cx + r, cy)
        p.drawLine(cx, cy - r, cx, cy + r)

        # Sweep
        a = math.radians(self.radar_angle)
        sx = cx + r * 0.9 * math.cos(a)
        sy = cy + r * 0.9 * math.sin(a)
        pen = QPen(_qc(RADAR, 180), 2)
        p.setPen(pen)
        p.drawLine(QPointF(cx, cy), QPointF(sx, sy))

        # Blips
        now = time.time()
        for blip in self.radar_blips:
            age = now - blip["time"]
            alpha = int(max(0, 255 * (1 - age / 5.0)))
            ba = math.radians(blip["angle"])
            dist = r * 0.5
            bx = cx + dist * math.cos(ba)
            by = cy + dist * math.sin(ba)
            p.setPen(Qt.NoPen)
            p.setBrush(_qc(ACCENT_GREEN, alpha))
            p.drawEllipse(QPointF(bx, by), 3, 3)

        # Label
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(QRectF(cx - r, cy + r + 5, r * 2, 15), Qt.AlignCenter, "RADAR")

    # ─── System Panel (Left) ─────────────────────────────

    def _draw_activity_panel(self, p: QPainter, x: int, y: int, w: int, h: int):
        # Panel background
        p.setPen(QPen(_qc(BORDER), 1))
        p.setBrush(_qc(BG_PANEL, 200))
        p.drawRect(x, y, w, h)

        # Title
        p.setPen(_qc(PRIMARY))
        p.setFont(self._font_title)
        p.drawText(QRectF(x, y + 8, w, 20), Qt.AlignCenter, "ACTIVITY CENTER")

        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(x + 10, y + 32, x + w - 10, y + 32)

        # ─── Section 1: Recent Commands ───
        sy = y + 45
        p.setPen(_qc(PRIMARY))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(x + 15, sy, "RECENT COMMANDS")
        sy += 15

        p.setFont(self._font_small)
        # Get last 5 commands
        recent = self.command_log[-5:] if self.command_log else []
        if not recent:
            p.setPen(_qc(TEXT_DIM))
            p.drawText(x + 15, sy, "No recent commands")
            sy += 20
        else:
            for entry in recent:
                cmd = entry.get("command", "")
                ts = entry.get("time", "")
                if len(cmd) > 22:
                    cmd = cmd[:19] + "..."
                p.setPen(_qc(TEXT_DIM))
                p.drawText(x + 15, sy, ts)
                p.setPen(_qc(SECONDARY))
                p.drawText(x + 85, sy, f"» {cmd}")
                sy += 16

        # ─── Section 2: Task Queue / Workflow ───
        sy += 10
        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(x + 10, sy, x + w - 10, sy)
        sy += 10

        p.setPen(_qc(PRIMARY))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(x + 15, sy, "TASK QUEUE & WORKFLOW")
        sy += 18

        # Display current active stage
        stage_label = getattr(self, "current_stage_label", "")
        if stage_label:
            p.setPen(_qc(ACCENT_GREEN))
            p.setFont(self._font_small)
            p.drawText(x + 15, sy, f"★ Active: {stage_label[:22]}")
            sy += 18
        else:
            p.setPen(_qc(TEXT_DIM))
            p.setFont(self._font_small)
            p.drawText(x + 15, sy, "★ Active: Idle")
            sy += 18

        # Static active systems
        p.setPen(_qc(TEXT_DIM))
        p.drawText(x + 15, sy, "⚙ Monitoring: Battery, CPU, RAM")
        sy += 16
        p.drawText(x + 15, sy, "⚙ Listening: Hey Jarvis (Vosk)")
        sy += 18

        # ─── Section 3: Reminders & Calendar ───
        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(x + 10, sy, x + w - 10, sy)
        sy += 10

        p.setPen(_qc(PRIMARY))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(x + 15, sy, "UPCOMING REMINDERS")
        sy += 18

        # Get schedules from brain
        try:
            from core.brain import get_schedules
            schedules = get_schedules()[:3]
        except Exception:
            schedules = []

        p.setFont(self._font_small)
        if not schedules:
            p.setPen(_qc(TEXT_DIM))
            p.drawText(x + 15, sy, "No upcoming reminders")
            sy += 20
        else:
            for sched in schedules:
                t = sched.get("time", "")
                r_name = sched.get("routine", "")
                if len(r_name) > 16:
                    r_name = r_name[:13] + "..."
                p.setPen(_qc(TEXT_DIM))
                p.drawText(x + 15, sy, t)
                p.setPen(_qc(TEXT))
                p.drawText(x + 80, sy, r_name)
                sy += 16

        # ─── Section 4: Notifications List ───
        sy += 10
        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(x + 10, sy, x + w - 10, sy)
        sy += 10

        p.setPen(_qc(PRIMARY))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(x + 15, sy, "NOTIFICATIONS")
        sy += 18

        p.setFont(self._font_small)
        notifs = list(self.notifications)[-3:]
        if not notifs:
            p.setPen(_qc(TEXT_DIM))
            p.drawText(x + 15, sy, "No notifications")
        else:
            for notif in notifs:
                msg = notif.get("message", "")
                if len(msg) > 24:
                    msg = msg[:21] + "..."
                p.setPen(_qc(notif.get("color", PRIMARY)))
                p.drawText(x + 15, sy, f"▸ {msg}")
                sy += 16

    def _draw_intelligence_panel(self, p: QPainter, x: int, y: int, w: int, h: int):
        # Panel background
        p.setPen(QPen(_qc(BORDER), 1))
        p.setBrush(_qc(BG_PANEL, 200))
        p.drawRect(x, y, w, h)

        # Title
        p.setPen(_qc(PRIMARY))
        p.setFont(self._font_title)
        p.drawText(QRectF(x, y + 8, w, 20), Qt.AlignCenter, "SYSTEM INTELLIGENCE")

        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(x + 10, y + 32, x + w - 10, y + 32)

        # ─── Labeled Meters ───
        cpu = self.stats.get("cpu_percent", 0)
        ram = self.stats.get("ram_percent", 0)
        gpu = self.stats.get("gpu_load", 0)
        bat = self.stats.get("battery_percent", 100)
        disk = self.stats.get("disk_percent", 0)

        self._draw_meter(p, x + 15, y + 50, w - 30, "CPU", cpu)
        self._draw_meter(p, x + 15, y + 90, w - 30, "RAM", ram)
        self._draw_meter(p, x + 15, y + 130, w - 30, "GPU", gpu)
        self._draw_meter(p, x + 15, y + 170, w - 30, "BATTERY", bat)
        self._draw_meter(p, x + 15, y + 210, w - 30, "DISK", disk)

        # Battery charging status
        if self.stats.get("battery_plugged", False):
            p.setPen(_qc(ACCENT_GREEN))
            p.setFont(self._font_main)
            p.drawText(x + w - 25, y + 182, "⚡")

        # ─── Network Status ───
        sy = y + 235
        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(x + 10, sy, x + w - 10, sy)
        sy += 5

        p.setPen(_qc(PRIMARY))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(QRectF(x, sy, w, 18), Qt.AlignCenter, "NETWORK INTELLIGENCE")
        sy += 20

        net = self.stats.get("network_connected", False)
        net_color = ACCENT_GREEN if net else ACCENT_RED
        net_text = "ONLINE" if net else "OFFLINE"

        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(x + 15, sy, "STATUS")
        p.setPen(_qc(net_color))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, net_text)
        sy += 16

        up = self.stats.get("net_upload_speed", 0.0)
        dn = self.stats.get("net_download_speed", 0.0)
        ping = self.stats.get("ping_ms", 0)

        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(x + 15, sy, "PING")
        p.setPen(_qc(TEXT))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, f"{ping}ms")
        sy += 16

        p.setPen(_qc(TEXT_DIM))
        p.drawText(x + 15, sy, "↑ UPLOAD")
        p.setPen(_qc(TEXT))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, f"{up:.1f} Mbps")
        sy += 16

        p.setPen(_qc(TEXT_DIM))
        p.drawText(x + 15, sy, "↓ DOWNLOAD")
        p.setPen(_qc(TEXT))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, f"{dn:.1f} Mbps")
        sy += 20

        # ─── OS Diagnostics (Mic / Speaker / Wake) ───
        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(x + 10, sy, x + w - 10, sy)
        sy += 5

        p.setPen(_qc(PRIMARY))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(QRectF(x, sy, w, 18), Qt.AlignCenter, "HARDWARE & OS STATUS")
        sy += 20

        # Mic Device
        mic_dev = self.stats.get("mic_device", "Default")
        if len(mic_dev) > 18:
            mic_dev = mic_dev[:15] + "..."
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(x + 15, sy, "MIC DEVICE")
        p.setPen(_qc(TEXT))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, mic_dev)
        sy += 16

        # Wake Word
        wake_status = self.stats.get("wake_word_status", "standby")
        p.setPen(_qc(TEXT_DIM))
        p.drawText(x + 15, sy, "WAKE ENGINE")
        p.setPen(_qc(ACCENT_GREEN if wake_status != "dead" else ACCENT_RED))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, "VOSK (ACTIVE)" if wake_status != "dead" else "OFFLINE")
        sy += 16

        # ─── AI Engine ───
        p.setPen(QPen(_qc(BORDER), 1))
        p.drawLine(x + 10, sy, x + w - 10, sy)
        sy += 5

        p.setPen(_qc(PRIMARY))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(QRectF(x, sy, w, 18), Qt.AlignCenter, "AI CORE")
        sy += 20

        ai_prov = self.stats.get("ai_status", "Gemini")
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(x + 15, sy, "PROVIDER")
        p.setPen(_qc(SECONDARY))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, ai_prov)
        sy += 16

        # Active Model
        p.setPen(_qc(TEXT_DIM))
        p.drawText(x + 15, sy, "ACTIVE MODEL")
        p.setPen(_qc(TEXT))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, "gemini-2.0-flash")
        sy += 16

        # Inference Time
        ai_lat = self.stats.get("ai_latency_ms", 0)
        p.setPen(_qc(TEXT_DIM))
        p.drawText(x + 15, sy, "INFERENCE")
        p.setPen(_qc(ACCENT_GREEN if ai_lat < 1000 else ACCENT_ORANGE))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, f"{ai_lat}ms" if ai_lat else "0ms")
        sy += 16

        # Memory size
        mem_stats = getattr(self, "_memory_stats", {})
        mem_total = mem_stats.get("total_entries", 0)
        p.setPen(_qc(TEXT_DIM))
        p.drawText(x + 15, sy, "MEM BANK SIZE")
        p.setPen(_qc(SECONDARY))
        p.drawText(QRectF(x + 15, sy - 2, w - 30, 18), Qt.AlignRight, f"{mem_total} entries")

    def _draw_bottom_panel(self, p: QPainter, x: int, y: int, w: int, h: int):
        # Panel frame
        p.setPen(QPen(_qc(BORDER), 1))
        p.setBrush(_qc(BG_PANEL, 150))
        p.drawRect(x, y, w, h)

        # Draw grid lines inside panel for futuristic look
        p.setPen(QPen(_qc(GRID, 80), 1))
        p.drawLine(x + w // 4, y, x + w // 4, y + h)
        p.drawLine(x + (2 * w) // 4, y, x + (2 * w) // 4, y + h)
        p.drawLine(x + (3 * w) // 4, y, x + (3 * w) // 4, y + h)

        # ─── Grid Sector 1: Latency ───
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(QRectF(x + 10, y + 10, w // 4 - 20, 15), Qt.AlignCenter, "RESPONSE TIME")
        
        exec_stats = getattr(self, "_exec_stats", {})
        last_latency = exec_stats.get("last_exec_time_ms", 0)
        p.setPen(_qc(PRIMARY))
        p.setFont(QFont("Consolas", 14, QFont.Bold))
        p.drawText(QRectF(x + 10, y + 30, w // 4 - 20, 25), Qt.AlignCenter, f"{last_latency}ms")

        # ─── Grid Sector 2: Pipeline State ───
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(QRectF(x + w // 4 + 10, y + 10, w // 4 - 20, 15), Qt.AlignCenter, "PIPELINE STAGE")
        
        stage = getattr(self, "current_stage", "idle").upper()
        stage_color = {
            "IDLE": PRIMARY_DIM, "LISTENING": PRIMARY,
            "UNDERSTANDING": SECONDARY, "THINKING": "#ffaa00",
            "EXECUTING": ACCENT_GREEN, "SPEAKING": REACTOR_CORE,
            "ERROR": ACCENT_RED,
        }.get(stage, PRIMARY_DIM)
        p.setPen(_qc(stage_color))
        p.setFont(QFont("Consolas", 11, QFont.Bold))
        p.drawText(QRectF(x + w // 4 + 10, y + 32, w // 4 - 20, 20), Qt.AlignCenter, stage)

        # ─── Grid Sector 3: Current Automation ───
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(QRectF(x + 2 * w // 4 + 10, y + 10, w // 4 - 20, 15), Qt.AlignCenter, "CURRENT AUTOMATION")
        
        automation_str = "STANDBY"
        if self.state == "executing":
            automation_str = "RUNNING HANDLER"
        elif self.state == "speaking":
            automation_str = "AUDIO STREAM"
        p.setPen(_qc(TEXT))
        p.setFont(QFont("Consolas", 10, QFont.Bold))
        p.drawText(QRectF(x + 2 * w // 4 + 10, y + 32, w // 4 - 20, 20), Qt.AlignCenter, automation_str)

        # ─── Grid Sector 4: System Health ───
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(QRectF(x + 3 * w // 4 + 10, y + 10, w // 4 - 20, 15), Qt.AlignCenter, "SYSTEM HEALTH")
        
        cpu = self.stats.get("cpu_percent", 0)
        ram = self.stats.get("ram_percent", 0)
        health_str = "NOMINAL"
        health_color = ACCENT_GREEN
        if cpu > 85 or ram > 85:
            health_str = "WARNING"
            health_color = ACCENT_ORANGE
        elif self.state == "error":
            health_str = "CRITICAL"
            health_color = ACCENT_RED
            
        p.setPen(_qc(health_color))
        p.setFont(QFont("Consolas", 12, QFont.Bold))
        p.drawText(QRectF(x + 3 * w // 4 + 10, y + 32, w // 4 - 20, 20), Qt.AlignCenter, health_str)

    def _draw_meter(self, p: QPainter, x: int, y: int, w: int, label: str, value: float):
        """Draw a labeled progress bar meter."""
        bar_h = 14
        pct = max(0, min(100, value))

        # Label
        p.setPen(_qc(TEXT_DIM))
        p.setFont(self._font_small)
        p.drawText(x, y, label)

        # Value
        p.setPen(_qc(TEXT))
        p.drawText(QRectF(x, y - 12, w, 14), Qt.AlignRight, f"{pct:.0f}%")

        # Bar background
        bar_y = y + 5
        p.setPen(Qt.NoPen)
        p.setBrush(_qc(GRID))
        p.drawRect(x, bar_y, w, bar_h)

        # Bar fill
        fill_w = int(w * pct / 100)
        if pct > 80:
            color = ACCENT_RED
        elif pct > 60:
            color = ACCENT_ORANGE
        else:
            color = PRIMARY
        p.setBrush(_qc(color, 200))
        p.drawRect(x, bar_y, fill_w, bar_h)

    # ─── Notifications ───────────────────────────────────

    def _draw_notifications(self, p: QPainter, w: int):
        now = time.time()
        x, y = w - 320, 120

        p.setFont(QFont("Consolas", 9))
        for notif in self.notifications:
            elapsed = now - notif["time"]
            if elapsed > notif["duration"]:
                continue
            alpha = int(255 * max(0.3, 1.0 - (elapsed / notif["duration"]) * 0.7))
            msg = notif["message"]
            if len(msg) > 40:
                msg = msg[:37] + "..."
            p.setPen(_qc(notif["color"], alpha))
            p.drawText(x, y, f"▸ {msg}")
            y += 22

    # ─── Conversation Display ────────────────────────────

    def _draw_conversation(self, p: QPainter, cx: int, base_y: int):
        entries = list(self.conversation)[-4:]
        p.setFont(QFont("Consolas", 9))
        for i, entry in enumerate(entries):
            y = base_y + i * 24
            speaker = entry["speaker"]
            text = entry["text"]
            if len(text) > 60:
                text = text[:57] + "..."
            if speaker == "You":
                color = SECONDARY
                prefix = "YOU »"
            else:
                color = PRIMARY
                prefix = "JARVIS »"
            p.setPen(_qc(color))
            p.drawText(QRectF(cx - 300, y, 600, 20), Qt.AlignCenter, f"{prefix} {text}")


# ═══════════════════════════════════════════════════════════
# Main HUD Window (QMainWindow)
# ═══════════════════════════════════════════════════════════

class TopBarProxy:
    """Provides .set_status() API for backward compatibility with jarvis.py."""
    def __init__(self, canvas: HUDCanvas):
        self._canvas = canvas

    def set_status(self, text: str):
        self._canvas._status_text = text


class JarvisHUD(QMainWindow):
    """
    Main application window — fullscreen Iron Man-style HUD.
    Drop-in replacement for the tkinter JarvisHUD.

    All public methods from the tkinter version are preserved:
    - update_state(), update_waveform(), update_system_stats()
    - update_command_log(), show_notification(), add_conversation()
    - add_radar_blip(), set_on_click(), set_on_text_command()
    - start_animation(), mainloop()
    """

    def __init__(self):
        # Create QApplication if it doesn't exist
        self._app = QApplication.instance()
        if self._app is None:
            self._app = QApplication(sys.argv)

        super().__init__()

        self.setWindowTitle("J.A.R.V.I.S.")
        self.setStyleSheet("background-color: #05080d;")

        # Screen dimensions
        screen = self._app.primaryScreen().geometry()
        self.w = screen.width()
        self.h = screen.height()

        self._is_fullscreen = True
        self._is_mini = False
        self._is_on_top = False

        # Central widget layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Canvas
        self.canvas = HUDCanvas()
        layout.addWidget(self.canvas, 1)

        # Input bar
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #0a1525;
                border-top: 1px solid #0a3040;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 5, 10, 5)

        self._input_entry = QLineEdit()
        self._input_entry.setPlaceholderText("Type a command...")
        self._input_entry.setStyleSheet("""
            QLineEdit {
                background-color: #0a1525;
                color: #00eaff;
                border: 1px solid #0a3040;
                border-radius: 4px;
                padding: 6px 12px;
                font-family: Consolas;
                font-size: 12px;
                selection-background-color: #005f6a;
            }
            QLineEdit:focus {
                border: 1px solid #00eaff;
            }
        """)
        self._input_entry.returnPressed.connect(self._on_text_submit)
        input_layout.addWidget(self._input_entry)

        send_btn = QPushButton("▶")
        send_btn.setFixedSize(40, 32)
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0a1525;
                color: #00eaff;
                border: 1px solid #0a3040;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0d1830;
                color: #00ff88;
                border: 1px solid #00eaff;
            }
        """)
        send_btn.clicked.connect(self._on_text_submit)
        input_layout.addWidget(send_btn)
        layout.addWidget(input_frame)

        # Top bar proxy (backward compat)
        self.top_bar = TopBarProxy(self.canvas)

        # Animation timer
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)
        self._last_time = time.time()
        self.fps_target = 30
        self._running = True

        # Callbacks
        self._on_click_callback: Optional[Callable] = None
        self._on_text_command_callback: Optional[Callable] = None
        self.canvas.clicked.connect(self._on_canvas_click)

        # Go fullscreen
        self.showFullScreen()

        log.info("PySide6 HUD initialized (%dx%d)", self.w, self.h)

    # ─── Animation ───────────────────────────────────────

    def start_animation(self):
        """Start the animation timer."""
        self._timer.start(int(1000 / self.fps_target))

    def _on_tick(self):
        """Animation tick — called by QTimer."""
        now = time.time()
        dt = now - self._last_time
        self._last_time = now
        self.canvas.update_animation(dt)

    # ─── Keyboard Shortcuts ──────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_Escape:
            self._on_close()
        elif key == Qt.Key_F11:
            self._toggle_fullscreen()
        elif key == Qt.Key_F10:
            self._toggle_mini_mode()
        elif key == Qt.Key_F9:
            self._toggle_always_on_top()
        else:
            super().keyPressEvent(event)

    def _toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        if self._is_fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
            self.resize(1280, 720)
        self.show_notification(
            "Fullscreen ON" if self._is_fullscreen else "Windowed mode", "info"
        )

    def _toggle_mini_mode(self):
        self._is_mini = not self._is_mini
        if self._is_mini:
            self.showNormal()
            self.resize(400, 200)
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.show()
            self.show_notification("Mini mode — F10 to expand", "info")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.showFullScreen()
            self._is_fullscreen = True
            self.show_notification("Full HUD restored", "info")

    def _toggle_always_on_top(self):
        self._is_on_top = not self._is_on_top
        if self._is_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()
        self.show_notification(
            "Pinned on top" if self._is_on_top else "Unpinned", "info"
        )

    # ─── Public Update Methods ───────────────────────────

    def update_state(self, state: str):
        """Update the HUD state (idle, listening, processing, speaking)."""
        self.canvas.state = state
        self.canvas.waveform_active = state in ("listening", "active_listening")
        status_map = {
            "idle": "SYSTEM ONLINE — STANDBY",
            "wake_listening": "SYSTEM ONLINE — STANDBY",
            "listening": "● ACTIVE LISTENING",
            "active_listening": "● ACTIVE LISTENING",
            "processing": "⚡ PROCESSING COMMAND",
            "speaking": "◆ RESPONDING",
            "sleeping": "○ SLEEP MODE",
        }
        self.canvas._status_text = status_map.get(state, "SYSTEM ONLINE")

    def update_waveform(self, levels: list[float]):
        """Update waveform visualization with audio levels."""
        self.canvas.waveform_levels = levels

    def update_system_stats(self, stats: dict):
        """Update system diagnostics panel."""
        self.canvas.stats = stats

    def update_command_log(self, entries: list[dict]):
        """Update the activity log panel."""
        self.canvas.command_log = entries

    def add_radar_blip(self, angle: Optional[int] = None):
        """Add a blip to the radar display."""
        if angle is None:
            angle = random.randint(0, 359)
        self.canvas.radar_blips.append({"angle": angle, "time": time.time()})

    def show_notification(self, message: str, level: str = "info"):
        """Show a toast notification on the HUD."""
        color_map = {
            "info": PRIMARY,
            "success": ACCENT_GREEN,
            "warning": "#ff9000",
            "error": "#ff0040",
        }
        self.canvas.notifications.append({
            "message": message,
            "color": color_map.get(level, PRIMARY),
            "time": time.time(),
            "duration": 4.0,
        })

    def add_conversation(self, speaker: str, text: str):
        """Add a conversation entry to the display."""
        self.canvas.conversation.append({
            "speaker": speaker,
            "text": text,
            "time": time.time(),
        })

    def update_memory_stats(self, stats: dict):
        """Update memory statistics for the system panel."""
        self.canvas._memory_stats = stats

    def update_exec_stats(self, stats: dict):
        """Update execution statistics for the system panel."""
        self.canvas._exec_stats = stats

    # ─── Callbacks ───────────────────────────────────────

    def set_on_click(self, callback: Callable):
        """Set callback for click-to-activate."""
        self._on_click_callback = callback

    def set_on_text_command(self, callback: Callable[[str], None]):
        """Set callback for text input commands."""
        self._on_text_command_callback = callback

    def _on_canvas_click(self):
        if self._on_click_callback:
            self._on_click_callback()

    def _on_text_submit(self):
        text = self._input_entry.text().strip()
        if not text:
            return
        self._input_entry.clear()
        self.add_conversation("You", text)
        if self._on_text_command_callback:
            import threading
            threading.Thread(
                target=self._on_text_command_callback,
                args=(text,),
                daemon=True,
            ).start()

    def _on_close(self):
        self._running = False
        self._timer.stop()
        self.close()

    # ─── Main Loop ───────────────────────────────────────

    def mainloop(self):
        """Start the Qt event loop (replaces tkinter mainloop)."""
        self._app.exec()

    def destroy(self):
        """Close and destroy the window."""
        self._on_close()
