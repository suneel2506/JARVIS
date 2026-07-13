"""
ui/waveform.py — Voice waveform visualization for Jarvis HUD.
"""
import math
import random
from ui.colors import WAVEFORM, WAVEFORM_DIM, PRIMARY_DIM, dim_color, lerp_color


class Waveform:
    def __init__(self, canvas, cx, cy, width=400, height=60, num_bars=32):
        self.canvas = canvas
        self.cx = cx
        self.cy = cy
        self.width = width
        self.height = height
        self.num_bars = num_bars
        self.levels = [0.0] * num_bars
        self.smooth_levels = [0.0] * num_bars
        self.active = False
        self.items = []

    def set_active(self, active):
        self.active = active

    def update_levels(self, levels):
        if len(levels) >= self.num_bars:
            self.levels = levels[:self.num_bars]
        else:
            ratio = len(levels) / self.num_bars
            self.levels = [
                levels[int(i * ratio)] if int(i * ratio) < len(levels) else 0
                for i in range(self.num_bars)
            ]
        for i in range(self.num_bars):
            self.smooth_levels[i] += (self.levels[i] - self.smooth_levels[i]) * 0.3

    def draw(self):
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

        cx, cy = self.cx, self.cy
        bar_w = self.width / self.num_bars * 0.7
        gap = self.width / self.num_bars * 0.3
        total = bar_w + gap
        start_x = cx - self.width / 2
        max_lev = max(max(self.smooth_levels), 0.001)

        for i in range(self.num_bars):
            lev = self.smooth_levels[i] / max_lev if self.active else 0
            if not self.active:
                lev = 0.05 + random.random() * 0.03
            bar_h = max(2, int(lev * self.height))
            x = start_x + i * total
            color = lerp_color(WAVEFORM_DIM, WAVEFORM, min(1.0, lev * 1.5)) if self.active else WAVEFORM_DIM
            item = self.canvas.create_rectangle(x, cy - bar_h, x + bar_w, cy, fill=color, outline="")
            self.items.append(item)
            mir_h = bar_h * 0.3
            item = self.canvas.create_rectangle(x, cy + 2, x + bar_w, cy + 2 + mir_h, fill=dim_color(color, 0.3), outline="")
            self.items.append(item)

        item = self.canvas.create_line(start_x - 10, cy, start_x + self.width + 10, cy, fill=PRIMARY_DIM, width=1)
        self.items.append(item)
