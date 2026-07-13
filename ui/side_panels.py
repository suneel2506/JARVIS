"""
ui/side_panels.py — Left and Right HUD panels for J.A.R.V.I.S.

Left: System diagnostics (CPU, RAM, GPU, Battery, Disk, Network, Temp, Speed, Ping, Active Window)
Right: Command activity log
"""
import math
from ui.colors import (
    PRIMARY, PRIMARY_DIM, SECONDARY, TEXT, TEXT_DIM, BG_PANEL,
    BORDER, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED, GRID, lerp_color
)


class SystemPanel:
    """Left panel: system diagnostics with GPU, temperature, net speed, and more."""

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
        gpu_load = self.stats.get("gpu_load", 0)
        bat = self.stats.get("battery_percent", 100)
        disk = self.stats.get("disk_percent", 0)
        net = self.stats.get("network_connected", False)

        self._draw_meter(x + 15, y + 50, w - 30, "CPU", cpu, f"{cpu:.0f}%")
        self._draw_meter(x + 15, y + 95, w - 30, "RAM", ram, f"{ram:.0f}%")
        self._draw_meter(x + 15, y + 140, w - 30, "GPU", gpu_load, f"{gpu_load:.0f}%")
        self._draw_meter(x + 15, y + 185, w - 30, "BATTERY", bat, f"{bat:.0f}%")
        self._draw_meter(x + 15, y + 230, w - 30, "DISK", disk, f"{disk:.0f}%")

        # Battery charging indicator
        bat_plugged = self.stats.get("battery_plugged", False)
        if bat_plugged:
            item = self.canvas.create_text(x + w - 15, y + 200, text="⚡", fill=ACCENT_GREEN, font=("Consolas", 10), anchor="e")
            self.items.append(item)

        # ─── Network Section ────────────────────────────
        section_y = y + 275
        item = self.canvas.create_line(x + 10, section_y, x + w - 10, section_y, fill=BORDER, width=1)
        self.items.append(item)
        item = self.canvas.create_text(x + w // 2, section_y + 12, text="NETWORK", fill=PRIMARY, font=("Consolas", 9, "bold"))
        self.items.append(item)

        # Connection status
        net_color = ACCENT_GREEN if net else ACCENT_RED
        net_text = "● CONNECTED" if net else "● OFFLINE"
        item = self.canvas.create_text(x + 15, section_y + 30, text="STATUS", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, section_y + 30, text=net_text, fill=net_color, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)

        # Upload/Download speed
        up_speed = self.stats.get("net_upload_speed", 0)
        down_speed = self.stats.get("net_download_speed", 0)
        item = self.canvas.create_text(x + 15, section_y + 46, text="↑ UPLOAD", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, section_y + 46, text=f"{up_speed:.1f} Mbps", fill=SECONDARY, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)
        item = self.canvas.create_text(x + 15, section_y + 62, text="↓ DOWNLOAD", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, section_y + 62, text=f"{down_speed:.1f} Mbps", fill=ACCENT_GREEN, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)

        # Ping
        ping = self.stats.get("ping_ms", 0)
        ping_color = ACCENT_GREEN if ping < 50 else ACCENT_ORANGE if ping < 150 else ACCENT_RED
        item = self.canvas.create_text(x + 15, section_y + 78, text="PING", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, section_y + 78, text=f"{ping}ms", fill=ping_color, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)

        # ─── Extra Info Section ─────────────────────────
        info_y = section_y + 100
        item = self.canvas.create_line(x + 10, info_y, x + w - 10, info_y, fill=BORDER, width=1)
        self.items.append(item)

        # Temperature
        cpu_temp = self.stats.get("cpu_temp", 0)
        gpu_temp = self.stats.get("gpu_temp", 0)
        if cpu_temp > 0:
            temp_color = ACCENT_GREEN if cpu_temp < 60 else ACCENT_ORANGE if cpu_temp < 80 else ACCENT_RED
            item = self.canvas.create_text(x + 15, info_y + 16, text="CPU TEMP", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
            self.items.append(item)
            item = self.canvas.create_text(x + w - 15, info_y + 16, text=f"{cpu_temp}°C", fill=temp_color, font=("Consolas", 8, "bold"), anchor="e")
            self.items.append(item)

        if gpu_temp > 0:
            temp_color = ACCENT_GREEN if gpu_temp < 70 else ACCENT_ORANGE if gpu_temp < 85 else ACCENT_RED
            item = self.canvas.create_text(x + 15, info_y + 32, text="GPU TEMP", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
            self.items.append(item)
            item = self.canvas.create_text(x + w - 15, info_y + 32, text=f"{gpu_temp}°C", fill=temp_color, font=("Consolas", 8, "bold"), anchor="e")
            self.items.append(item)

        # Mic status
        mic_state = self.stats.get("mic_state", "standby")
        mic_colors = {"standby": PRIMARY_DIM, "listening": ACCENT_GREEN, "active_listening": ACCENT_GREEN, "processing": ACCENT_ORANGE, "sleeping": ACCENT_ORANGE}
        mic_labels = {"standby": "● STANDBY", "listening": "● ACTIVE", "active_listening": "● ACTIVE", "processing": "● BUSY", "sleeping": "● SLEEPING"}
        mic_color = mic_colors.get(mic_state, PRIMARY_DIM)
        mic_label = mic_labels.get(mic_state, "● STANDBY")
        item = self.canvas.create_text(x + 15, info_y + 52, text="MIC", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, info_y + 52, text=mic_label, fill=mic_color, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)

        # Process count
        proc_count = self.stats.get("process_count", 0)
        item = self.canvas.create_text(x + 15, info_y + 68, text="PROCESSES", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, info_y + 68, text=str(proc_count), fill=TEXT, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)

        # Uptime
        uptime = self.stats.get("uptime_hours", 0)
        if uptime >= 24:
            uptime_str = f"{int(uptime // 24)}d {int(uptime % 24)}h"
        else:
            uptime_str = f"{int(uptime)}h {int((uptime % 1) * 60)}m"
        item = self.canvas.create_text(x + 15, info_y + 84, text="UPTIME", fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + w - 15, info_y + 84, text=uptime_str, fill=TEXT, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)

        # CPU History graph
        self._draw_cpu_graph(x + 15, info_y + 105, w - 30, 60)

        # Active window
        active_win = self.stats.get("active_window", "")
        if active_win:
            graph_bottom = info_y + 105 + 14 + 60 + 10
            item = self.canvas.create_text(x + 15, graph_bottom, text="ACTIVE", fill=TEXT_DIM, font=("Consolas", 7), anchor="w")
            self.items.append(item)
            if len(active_win) > 25:
                active_win = active_win[:22] + "..."
            item = self.canvas.create_text(x + 15, graph_bottom + 14, text=active_win, fill=SECONDARY, font=("Consolas", 7), anchor="w")
            self.items.append(item)

        # System info at bottom
        hostname = self.stats.get("hostname", "N/A")
        os_name = self.stats.get("os_name", "N/A")
        ip = self.stats.get("ip_address", "N/A")
        bottom_y = y + self.height - 60
        item = self.canvas.create_text(x + 15, bottom_y, text=f"HOST: {hostname}", fill=TEXT_DIM, font=("Consolas", 7), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + 15, bottom_y + 14, text=f"OS: {os_name}", fill=TEXT_DIM, font=("Consolas", 7), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + 15, bottom_y + 28, text=f"IP: {ip}", fill=TEXT_DIM, font=("Consolas", 7), anchor="w")
        self.items.append(item)

    def _draw_meter(self, x, y, width, label, value, value_text):
        """Draw a horizontal progress bar with label."""
        bar_h = 14
        item = self.canvas.create_text(x, y, text=label, fill=TEXT_DIM, font=("Consolas", 8), anchor="w")
        self.items.append(item)
        item = self.canvas.create_text(x + width, y, text=value_text, fill=TEXT, font=("Consolas", 8, "bold"), anchor="e")
        self.items.append(item)
        bar_y = y + 12
        item = self.canvas.create_rectangle(x, bar_y, x + width, bar_y + bar_h, fill=GRID, outline=BORDER, width=1)
        self.items.append(item)
        fill_w = max(1, int(width * value / 100))
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

        # Log entries
        max_entries = (self.height - 60) // 40
        entries = self.log_entries[-max_entries:] if self.log_entries else []

        for i, entry in enumerate(entries):
            ey = y + 45 + i * 40
            time_str = entry.get("time", "")
            cmd = entry.get("command", "")
            resp = entry.get("response", "")

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
