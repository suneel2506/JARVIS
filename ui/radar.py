"""
ui/radar.py — Rotating radar sweep animation for Jarvis HUD.
"""
import math
import time
from ui.colors import RADAR, RADAR_DIM, PRIMARY_DIM, BORDER, dim_color


class Radar:
    def __init__(self, canvas, cx, cy, radius=70):
        self.canvas = canvas
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.angle = 0
        self.items = []
        self.blips = []

    def add_blip(self, angle_deg):
        self.blips.append({"angle": angle_deg, "life": 1.0})

    def update(self, dt):
        self.angle += 60 * dt
        if self.angle >= 360:
            self.angle -= 360
        for b in self.blips:
            b["life"] -= 0.3 * dt
        self.blips = [b for b in self.blips if b["life"] > 0]

    def draw(self):
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

        cx, cy, r = self.cx, self.cy, self.radius

        # Background circle
        item = self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=RADAR_DIM, outline=BORDER, width=1)
        self.items.append(item)

        # Grid circles
        for ring in [0.33, 0.66, 1.0]:
            rr = int(r * ring)
            item = self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=dim_color(RADAR, 0.2), width=1)
            self.items.append(item)

        # Cross lines
        item = self.canvas.create_line(cx - r, cy, cx + r, cy, fill=dim_color(RADAR, 0.15), width=1)
        self.items.append(item)
        item = self.canvas.create_line(cx, cy - r, cx, cy + r, fill=dim_color(RADAR, 0.15), width=1)
        self.items.append(item)

        # Sweep line
        a = math.radians(self.angle)
        x2 = cx + r * math.cos(a)
        y2 = cy - r * math.sin(a)
        item = self.canvas.create_line(cx, cy, x2, y2, fill=RADAR, width=2)
        self.items.append(item)

        # Sweep trail (fading arc)
        for i in range(8):
            trail_a = math.radians(self.angle - i * 5)
            tx = cx + r * 0.95 * math.cos(trail_a)
            ty = cy - r * 0.95 * math.sin(trail_a)
            dot_r = 2
            color = dim_color(RADAR, 0.4 - i * 0.04)
            item = self.canvas.create_oval(tx - dot_r, ty - dot_r, tx + dot_r, ty + dot_r, fill=color, outline="")
            self.items.append(item)

        # Blips
        for b in self.blips:
            ba = math.radians(b["angle"])
            bx = cx + r * 0.6 * math.cos(ba)
            by = cy - r * 0.6 * math.sin(ba)
            br = 3
            color = dim_color(RADAR, b["life"])
            item = self.canvas.create_oval(bx - br, by - br, bx + br, by + br, fill=color, outline="")
            self.items.append(item)

        # Label
        item = self.canvas.create_text(cx, cy + r + 14, text="SCAN", fill=PRIMARY_DIM, font=("Consolas", 8))
        self.items.append(item)
