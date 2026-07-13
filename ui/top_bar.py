"""
ui/top_bar.py — Top bar HUD element for Jarvis.
Shows time, date, status, and angled connector lines.
"""
import math
import time as time_mod
from datetime import datetime
from ui.colors import PRIMARY, PRIMARY_DIM, TEXT, TEXT_DIM, BG, BORDER, BORDER_BRIGHT, SECONDARY


class TopBar:
    """
    Draws the top bar: clock, date, status text, and decorative HUD lines.
    """

    def __init__(self, canvas, width, height=100):
        self.canvas = canvas
        self.width = width
        self.height = height
        self.status_text = "SYSTEM ONLINE"
        self.items = []

    def set_status(self, text):
        self.status_text = text.upper()

    def draw(self):
        """Draw the top bar."""
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

        w = self.width
        cx = w // 2
        now = datetime.now()

        # ─── Top border line ────────────────────────────
        item = self.canvas.create_line(0, 2, w, 2, fill=BORDER, width=1)
        self.items.append(item)
        item = self.canvas.create_line(0, 4, w, 4, fill=PRIMARY_DIM, width=1)
        self.items.append(item)

        # ─── Angled connector lines (Iron Man HUD style) ─
        # Left connector
        points = [cx - 250, 5, cx - 180, 65]
        item = self.canvas.create_line(*points, fill=PRIMARY_DIM, width=2)
        self.items.append(item)

        # Right connector
        points = [cx + 250, 5, cx + 180, 65]
        item = self.canvas.create_line(*points, fill=PRIMARY_DIM, width=2)
        self.items.append(item)

        # Horizontal connector lines
        item = self.canvas.create_line(cx - 180, 65, cx - 160, 65, fill=PRIMARY, width=2)
        self.items.append(item)
        item = self.canvas.create_line(cx + 180, 65, cx + 160, 65, fill=PRIMARY, width=2)
        self.items.append(item)

        # ─── "J.A.R.V.I.S." title ──────────────────────
        item = self.canvas.create_text(
            cx, 22,
            text="J . A . R . V . I . S .",
            fill=PRIMARY_DIM,
            font=("Consolas", 10, "bold"),
        )
        self.items.append(item)

        # ─── Time display ───────────────────────────────
        time_str = now.strftime("%H:%M:%S")
        item = self.canvas.create_text(
            cx, 48,
            text=time_str,
            fill=PRIMARY,
            font=("Consolas", 32, "bold"),
        )
        self.items.append(item)

        # ─── Date display ───────────────────────────────
        date_str = now.strftime("%A, %B %d, %Y")
        item = self.canvas.create_text(
            cx, 78,
            text=date_str.upper(),
            fill=TEXT_DIM,
            font=("Consolas", 10),
        )
        self.items.append(item)

        # ─── Status indicator ───────────────────────────
        item = self.canvas.create_text(
            cx, 95,
            text=self.status_text,
            fill=SECONDARY,
            font=("Consolas", 9, "bold"),
        )
        self.items.append(item)

        # ─── Corner accents ─────────────────────────────
        # Top-left corner
        self._draw_corner(15, 10, "tl")
        # Top-right corner
        self._draw_corner(w - 15, 10, "tr")

        # ─── Side status indicators ─────────────────────
        # Left: MARK II label
        item = self.canvas.create_text(
            80, 30,
            text="MARK II",
            fill=TEXT_DIM,
            font=("Consolas", 9),
            anchor="w",
        )
        self.items.append(item)

        # Right: system label
        item = self.canvas.create_text(
            w - 80, 30,
            text="v2.0",
            fill=TEXT_DIM,
            font=("Consolas", 9),
            anchor="e",
        )
        self.items.append(item)

    def _draw_corner(self, x, y, corner_type):
        """Draw a small corner accent."""
        size = 20
        if corner_type == "tl":
            # Top-left L shape
            item = self.canvas.create_line(x, y, x + size, y, fill=PRIMARY, width=2)
            self.items.append(item)
            item = self.canvas.create_line(x, y, x, y + size, fill=PRIMARY, width=2)
            self.items.append(item)
        elif corner_type == "tr":
            item = self.canvas.create_line(x, y, x - size, y, fill=PRIMARY, width=2)
            self.items.append(item)
            item = self.canvas.create_line(x, y, x, y + size, fill=PRIMARY, width=2)
            self.items.append(item)
