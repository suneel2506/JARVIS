"""
ui/side_panels.py — Left and Right HUD panels for J.A.R.V.I.S.

Left: System diagnostics (CPU, RAM, Battery, Disk, Network, Mic status)
Right: Command activity log
"""
import math
from ui.colors import (
    PRIMARY, PRIMARY_DIM, SECONDARY, TEXT, TEXT_DIM, BG_PANEL,
    BORDER, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED, GRID, lerp_color
)


class SystemPanel:
    """Left panel: system diagnostics."""

    def __init__(self, canvas, x, y, width, height):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.stats = {}
        self.items = []

    def update_stats(self, stats):
        self.stats = stats

    def draw(self):
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

        x, y, w = self.x, self.y, self.width

        # Panel background
        item = self.canvas.create_rectangle(x, y, x + w, y + self.height, fill=BG_PANEL, outline=BORDER, width=1)
        self.items.append(item)

        # Title
        item = self.canvas.create_text(x + w // 2, y + 18, text="SYSTEM DIAGNOSTICS", fill=PRIMARY, font=("Consolas", 10, "bold"))
        self.items.append(item)

        # Separator
        item = self.canvas.create_line(x + 10, y + 32, x + w - 10, y + 32, fill=BORDER, width=1)
        self.items.append(item)

        # Draw meters
        cpu = self.stats.get("cpu_percent", 0)
        ram = self.stats.get("ram_percent", 0)
        bat = self.stats.get("battery_percent", 100)
        disk = self.stats.get("disk_percent", 0)
        net = self.stats.get("network_connected", False)

        self._draw_meter(x + 15, y + 50, w - 30, "CPU", cpu, f"{cpu:.0f}%")
        self._draw_meter(x + 15, y + 100, w - 30, "RAM", ram, f"{ram:.0f}%")
        self._draw_meter(x + 15, y + 150, w - 30, "BATTERY", bat, f"{bat:.0f}%")
        self._draw_meter(x + 15, y + 200, w - 30, "DISK", disk, f"{disk:.0f}%")

        # Network status
        net_color = ACCENT_GREEN if net else ACCENT_RED
        net_text = "● CONNECTED" if net else "● OFFLINE"
        item = self.canvas.create_text(x + 15, y + 248, text="NETWORK", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, y + 248, text=net_text, fill=net_color, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)

        # Battery charging indicator
        bat_plugged = self.stats.get("battery_plugged", False)
        if bat_plugged:
            item = self.canvas.create_text(x + w - 15, y + 165, text="⚡", fill=ACCENT_GREEN, font=("Consolas", 10), anchor="e")
            self.items.append(item)

        # Mic status
        mic_state = self.stats.get("mic_state", "standby")
        mic_colors = {"standby": PRIMARY_DIM, "listening": ACCENT_GREEN, "active_listening": ACCENT_GREEN, "processing": ACCENT_ORANGE}
        mic_labels = {"standby": "● STANDBY", "listening": "● ACTIVE", "active_listening": "● ACTIVE", "processing": "● BUSY"}
        mic_color = mic_colors.get(mic_state, PRIMARY_DIM)
        mic_label = mic_labels.get(mic_state, "● STANDBY")
        item = self.canvas.create_text(x + 15, y + 268, text="MIC", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, y + 268, text=mic_label, fill=mic_color, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)

        # CPU History graph
        self._draw_cpu_graph(x + 15, y + 295, w - 30, 80)

        # System info
        hostname = self.stats.get("hostname", "N/A")
        os_name = self.stats.get("os_name", "N/A")
        ip = self.stats.get("ip_address", "N/A")
        info_y = y + 395
        item = self.canvas.create_text(x + 15, info_y, text=f"HOST: {hostname}", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + 15, info_y + 16, text=f"OS: {os_name}", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + 15, info_y + 32, text=f"IP: {ip}", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)

    def _draw_meter(self, x, y, width, label, value, value_text):
        """Draw a horizontal progress bar with label."""
        bar_h = 14
        # Label
        item = self.canvas.create_text(x, y, text=label, fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        # Value text
        item = self.canvas.create_text(x + width, y, text=value_text, fill=TEXT, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)
        # Bar background
        bar_y = y + 12
        item = self.canvas.create_rectangle(x, bar_y, x + width, bar_y + bar_h, fill=GRID, outline=BORDER, width=1)
        self.items.append(item)
        # Bar fill
        fill_w = max(1, int(width * value / 100))
        # Color changes based on value
        if value > 90:
            color = ACCENT_RED
        elif value > 70:
            color = ACCENT_ORANGE
        else:
            color = PRIMARY
        item = self.canvas.create_rectangle(x + 1, bar_y + 1, x + fill_w, bar_y + bar_h - 1, fill=color, outline="")
        self.items.append(item)

    def _draw_cpu_graph(self, x, y, width, height):
        """Draw a small CPU history line graph."""
        item = self.canvas.create_text(x, y, text="[CPU HISTORY]", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        graph_y = y + 14
        item = self.canvas.create_rectangle(x, graph_y, x + width, graph_y + height, fill=GRID, outline=BORDER, width=1)
        self.items.append(item)

        history = self.stats.get("cpu_history", [0] * 30)
        if len(history) < 2:
            return
        step = width / (len(history) - 1)
        points = []
        for i, val in enumerate(history):
            px = x + i * step
            py = graph_y + height - (val / 100 * height)
            points.append(px)
            points.append(py)
        if len(points) >= 4:
            item = self.canvas.create_line(*points, fill=PRIMARY, width=1, smooth=True)
            self.items.append(item)


class LogPanel:
    """Right panel: command activity log."""

    def __init__(self, canvas, x, y, width, height):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.log_entries = []
        self.items = []

    def update_log(self, entries):
        self.log_entries = entries

    def draw(self):
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

        x, y, w = self.x, self.y, self.width

        # Panel background
        item = self.canvas.create_rectangle(x, y, x + w, y + self.height, fill=BG_PANEL, outline=BORDER, width=1)
        self.items.append(item)

        # Title
        item = self.canvas.create_text(x + w // 2, y + 18, text="ACTIVITY LOG", fill=PRIMARY, font=("Consolas", 10, "bold"))
        self.items.append(item)

        # Separator
        item = self.canvas.create_line(x + 10, y + 32, x + w - 10, y + 32, fill=BORDER, width=1)
        self.items.append(item)

        # Log entries (show last N that fit)
        max_entries = (self.height - 60) // 40
        entries = self.log_entries[-max_entries:] if self.log_entries else []

        for i, entry in enumerate(entries):
            ey = y + 45 + i * 40
            time_str = entry.get("time", "")
            cmd = entry.get("command", "")
            resp = entry.get("response", "")

            # Truncate
            if len(cmd) > 28:
                cmd = cmd[:25] + "..."
            if len(resp) > 28:
                resp = resp[:25] + "..."

            item = self.canvas.create_text(x + 10, ey, text=f"[{time_str}]", fill=TEXT_DIM, font=("Consolas", 7), anchor="w")
            self.items.append(item)
            item = self.canvas.create_text(x + 10, ey + 13, text=f"» {cmd}", fill=SECONDARY, font=("Consolas", 8), anchor="w")
            self.items.append(item)
            item = self.canvas.create_text(x + 10, ey + 26, text=f"  {resp}", fill=TEXT_DIM, font=("Consolas", 7), anchor="w")
            self.items.append(item)

        if not entries:
            item = self.canvas.create_text(x + w // 2, y + 80, text='Say "Hey Jarvis"\nto get started', fill=TEXT_DIM, font=("Consolas", 9), justify="center")
            self.items.append(item)

        # Bottom: instructions
        item = self.canvas.create_text(x + w // 2, y + self.height - 20,
                                       text="CLICK ANYWHERE TO ACTIVATE",
                                       fill=PRIMARY_DIM, font=("Consolas", 8))
        self.items.append(item)
