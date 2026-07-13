"""
ui/arc_reactor.py — Animated Iron Man Arc Reactor for the HUD center.

Draws concentric rotating rings, tick marks, and a pulsing core on a tkinter Canvas.
Supports distinct visual states: idle, listening, processing, speaking.
"""
import math
from ui.colors import (
    REACTOR_CORE, REACTOR_RING, REACTOR_OUTER, PRIMARY, PRIMARY_DIM,
    SECONDARY, TEXT, lerp_color, dim_color
)


class ArcReactor:
    """
    Draws and animates an Iron Man-style arc reactor on a tkinter Canvas.

    States:
    - idle: Slow rotation, dim core pulse
    - listening: Medium rotation, bright cyan core
    - processing: Fast rotation, orange/amber pulsating core
    - speaking: Rhythmic pulse with bright white-cyan core
    """

    def __init__(self, canvas, cx: int, cy: int, radius: int = 120) -> None:
        self.canvas = canvas
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.angle1: float = 0       # Outer ring rotation
        self.angle2: float = 0       # Middle ring rotation
        self.angle3: float = 0       # Inner ring rotation
        self.pulse: float = 0        # Pulse phase (0..2π)
        self.state: str = "idle"
        self.items: list[int] = []   # Canvas item IDs for cleanup

    def set_state(self, state: str) -> None:
        """Set the reactor visual state."""
        self.state = state

    def update(self, dt: float) -> None:
        """Update animation state. dt = seconds since last frame."""
        speed_table = {
            "listening":        (3.0, -4.5, 6.0, 4.0),
            "active_listening": (3.0, -4.5, 6.0, 4.0),
            "processing":       (5.0, -7.0, 9.0, 6.0),
            "speaking":         (2.0, -3.0, 4.0, 5.0),
        }
        s1, s2, s3, sp = speed_table.get(self.state, (0.5, -0.3, 0.2, 3.0))

        self.angle1 += s1 * dt * 60
        self.angle2 += s2 * dt * 60
        self.angle3 += s3 * dt * 60
        self.pulse += sp * dt
        if self.pulse > math.pi * 2:
            self.pulse -= math.pi * 2

    def draw(self) -> None:
        """Draw the arc reactor on the canvas."""
        # Clear previous items
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

        cx, cy, r = self.cx, self.cy, self.radius

        # ─── Outer decorative ring (thin) ────────────────
        self._draw_ring(cx, cy, r + 20, r + 22, REACTOR_OUTER, 16, self.angle1)

        # ─── Outer segmented ring ────────────────────────
        self._draw_segmented_ring(cx, cy, r, r + 10, REACTOR_RING, 12, self.angle1, gap=15)

        # ─── Middle tick ring ────────────────────────────
        self._draw_tick_ring(cx, cy, r - 10, r - 2, PRIMARY_DIM, 36, self.angle2)

        # ─── Inner segmented ring ────────────────────────
        self._draw_segmented_ring(cx, cy, r - 30, r - 18, SECONDARY, 8, self.angle3, gap=20)

        # ─── Inner tick ring ─────────────────────────────
        self._draw_tick_ring(cx, cy, r - 45, r - 35, PRIMARY_DIM, 24, -self.angle3)

        # ─── Core glow ──────────────────────────────────
        pulse_val = (math.sin(self.pulse) + 1) / 2  # 0..1

        if self.state in ("listening", "active_listening"):
            core_color = lerp_color(REACTOR_CORE, "#ffffff", pulse_val * 0.5)
            core_r = int(r * 0.22 + pulse_val * 8)
        elif self.state == "processing":
            core_color = lerp_color(REACTOR_CORE, "#ffaa00", pulse_val * 0.7)
            core_r = int(r * 0.22 + pulse_val * 12)
        elif self.state == "speaking":
            # Rhythmic speaking pulse — bright cyan-white with distinct beat
            beat = (math.sin(self.pulse * 2) + 1) / 2  # Double frequency
            core_color = lerp_color(REACTOR_CORE, "#e0ffff", beat * 0.6)
            core_r = int(r * 0.22 + beat * 10)
        else:  # idle
            core_color = lerp_color(REACTOR_CORE, PRIMARY, pulse_val * 0.3)
            core_r = int(r * 0.20 + pulse_val * 4)

        # Outer glow halo
        for i in range(3):
            glow_r = core_r + (3 - i) * 8
            glow_color = dim_color(core_color, 0.15 + i * 0.05)
            item = self.canvas.create_oval(
                cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r,
                fill=glow_color, outline="", width=0,
            )
            self.items.append(item)

        # Core circle
        item = self.canvas.create_oval(
            cx - core_r, cy - core_r, cx + core_r, cy + core_r,
            fill=core_color, outline=dim_color(core_color, 0.7), width=2,
        )
        self.items.append(item)

        # Center dot
        dot_r = core_r // 3
        item = self.canvas.create_oval(
            cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r,
            fill="#ffffff", outline="",
        )
        self.items.append(item)

        # ─── State text below reactor ────────────────────
        state_text = {
            "idle": "STANDBY",
            "wake_listening": "STANDBY",
            "listening": "● LISTENING",
            "active_listening": "● LISTENING",
            "processing": "⚡ PROCESSING",
            "speaking": "◆ SPEAKING",
        }.get(self.state, "STANDBY")

        state_color = {
            "idle": PRIMARY_DIM,
            "wake_listening": PRIMARY_DIM,
            "listening": PRIMARY,
            "active_listening": PRIMARY,
            "processing": "#ffaa00",
            "speaking": REACTOR_CORE,
        }.get(self.state, PRIMARY_DIM)

        item = self.canvas.create_text(
            cx, cy + r + 45,
            text=state_text,
            fill=state_color,
            font=("Consolas", 12, "bold"),
        )
        self.items.append(item)

    def _draw_ring(self, cx, cy, r_inner, r_outer, color, segments, angle_offset):
        """Draw a thin decorative ring of dots."""
        for i in range(segments):
            a = math.radians(angle_offset + i * (360 / segments))
            x = cx + (r_inner + r_outer) / 2 * math.cos(a)
            y = cy + (r_inner + r_outer) / 2 * math.sin(a)
            dot_r = 2
            item = self.canvas.create_oval(
                x - dot_r, y - dot_r, x + dot_r, y + dot_r,
                fill=color, outline="",
            )
            self.items.append(item)

    def _draw_segmented_ring(self, cx, cy, r_inner, r_outer, color, num_segments, angle_offset, gap=10):
        """Draw segmented arcs forming a ring."""
        segment_angle = 360 / num_segments - gap
        for i in range(num_segments):
            start = angle_offset + i * (360 / num_segments)
            item = self.canvas.create_arc(
                cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer,
                start=start, extent=segment_angle,
                style="arc", outline=color, width=3,
            )
            self.items.append(item)

    def _draw_tick_ring(self, cx, cy, r_inner, r_outer, color, num_ticks, angle_offset):
        """Draw tick marks in a ring."""
        for i in range(num_ticks):
            a = math.radians(angle_offset + i * (360 / num_ticks))
            x1 = cx + r_inner * math.cos(a)
            y1 = cy + r_inner * math.sin(a)
            x2 = cx + r_outer * math.cos(a)
            y2 = cy + r_outer * math.sin(a)
            item = self.canvas.create_line(
                x1, y1, x2, y2,
                fill=color, width=1,
            )
            self.items.append(item)
