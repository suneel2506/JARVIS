"""
ui/hud.py — Main fullscreen Iron Man HUD for J.A.R.V.I.S.

Composites all UI elements on a single tkinter Canvas with 30fps animation.
Features:
- Arc reactor with state-driven animations
- Voice waveform visualization
- Radar sweep with command blips
- System diagnostics panel (CPU, RAM, GPU, Battery, Disk, Network, Speed, Ping)
- Activity log panel
- Text input bar for typed commands
- Toast notification system
- Conversation display
- Floating holographic particles
- Keyboard shortcuts (F11 fullscreen, F10 mini mode, F9 always-on-top)
"""
import tkinter as tk
import time
import math
import random
from collections import deque
from typing import Optional, Callable

from ui.colors import BG, PRIMARY, PRIMARY_DIM, TEXT, TEXT_DIM, SECONDARY, BORDER, ACCENT_GREEN
from ui.arc_reactor import ArcReactor
from ui.top_bar import TopBar
from ui.side_panels import SystemPanel, LogPanel
from ui.waveform import Waveform
from ui.radar import Radar
from ui.particles import ParticleSystem


class JarvisHUD(tk.Tk):
    """
    Main application window — fullscreen Iron Man-style HUD.

    Manages the animation loop, UI components, text input, notification
    system, and particle effects. All backend interaction is through callbacks.
    """

    def __init__(self) -> None:
        super().__init__()

        # Window setup
        self.title("J.A.R.V.I.S.")
        self.attributes('-fullscreen', True)
        self.configure(bg=BG)
        self.bind('<Escape>', lambda e: self._on_close())
        self.bind('<Button-1>', self._on_click)

        # Keyboard shortcuts
        self.bind('<F11>', self._toggle_fullscreen)
        self.bind('<F10>', self._toggle_mini_mode)
        self.bind('<F9>', self._toggle_always_on_top)

        # Screen dimensions
        self.w: int = self.winfo_screenwidth()
        self.h: int = self.winfo_screenheight()
        self._is_fullscreen: bool = True
        self._is_mini: bool = False
        self._is_on_top: bool = False

        # Main canvas
        self.canvas = tk.Canvas(
            self, width=self.w, height=self.h,
            bg=BG, highlightthickness=0,
        )
        self.canvas.pack()

        # Draw background grid
        self._draw_background_grid()

        # Initialize UI components
        panel_w = int(self.w * 0.20)
        panel_h = self.h - 140
        center_x = self.w // 2
        center_y = self.h // 2

        self.top_bar = TopBar(self.canvas, self.w)
        self.arc_reactor = ArcReactor(
            self.canvas, center_x, center_y - 30,
            radius=min(140, self.h // 5),
        )
        self.waveform = Waveform(
            self.canvas, center_x,
            center_y + self.arc_reactor.radius + 90,
            width=min(450, self.w // 3), num_bars=32,
        )
        self.system_panel = SystemPanel(self.canvas, 20, 110, panel_w, panel_h)
        self.log_panel = LogPanel(self.canvas, self.w - panel_w - 20, 110, panel_w, panel_h)
        self.radar = Radar(self.canvas, 140, self.h - 120, radius=60)

        # Particle system
        self.particles = ParticleSystem(self.canvas, self.w, self.h, max_particles=35)

        # ─── Text Input Bar ─────────────────────────────
        self._input_frame = tk.Frame(self, bg="#0a1525", bd=0, highlightthickness=0)
        self._input_frame.place(
            x=panel_w + 40, y=self.h - 55,
            width=self.w - 2 * panel_w - 80, height=40,
        )

        # Input field
        self._input_var = tk.StringVar()
        self._input_entry = tk.Entry(
            self._input_frame,
            textvariable=self._input_var,
            bg="#0a1525", fg=PRIMARY, insertbackground=PRIMARY,
            font=("Consolas", 12), bd=0,
            highlightthickness=1, highlightcolor=PRIMARY_DIM,
            highlightbackground=BORDER,
        )
        self._input_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 5), pady=5)
        self._input_entry.bind('<Return>', self._on_text_submit)
        self._input_entry.bind('<FocusIn>', lambda e: None)

        # Send button
        self._send_btn = tk.Button(
            self._input_frame,
            text="▶", bg="#0a1525", fg=PRIMARY,
            font=("Consolas", 14, "bold"), bd=0,
            activebackground="#0d1830", activeforeground=ACCENT_GREEN,
            command=lambda: self._on_text_submit(None),
            cursor="hand2",
        )
        self._send_btn.pack(side=tk.RIGHT, padx=(0, 10))

        # Placeholder text
        self._input_entry.insert(0, "Type a command...")
        self._input_entry.config(fg=TEXT_DIM)
        self._input_entry.bind('<FocusIn>', self._on_input_focus)
        self._input_entry.bind('<FocusOut>', self._on_input_blur)

        # ─── Notification System ────────────────────────
        self._notifications: deque[dict] = deque(maxlen=5)
        self._notification_items: list[int] = []

        # ─── Conversation Display ───────────────────────
        self._conversation: deque[dict] = deque(maxlen=8)
        self._conversation_items: list[int] = []

        # Bottom decorative text
        self.canvas.create_text(
            center_x, self.h - 12,
            text="J.A.R.V.I.S. — Just A Rather Very Intelligent System  │  F11 Fullscreen  │  F10 Mini  │  F9 Pin  │  ESC Exit",
            fill=TEXT_DIM, font=("Consolas", 8),
        )

        # Animation timing
        self.last_time: float = time.time()
        self.fps_target: int = 30
        self._running: bool = True

        # Callbacks
        self._on_click_callback: Optional[Callable] = None
        self._on_text_command_callback: Optional[Callable] = None

    def set_on_click(self, callback: Callable) -> None:
        """Set callback for click-to-activate."""
        self._on_click_callback = callback

    def set_on_text_command(self, callback: Callable[[str], None]) -> None:
        """Set callback for text input commands."""
        self._on_text_command_callback = callback

    def _draw_background_grid(self) -> None:
        """Draw a subtle background grid for the HUD effect."""
        grid_color = "#0a0f18"
        spacing = 60
        for x in range(0, self.w, spacing):
            self.canvas.create_line(x, 0, x, self.h, fill=grid_color, width=1)
        for y in range(0, self.h, spacing):
            self.canvas.create_line(0, y, self.w, y, fill=grid_color, width=1)

    def _on_click(self, event: tk.Event) -> None:
        """Handle canvas click — activate voice listening."""
        if event.widget != self.canvas:
            return
        if self._on_click_callback:
            self._on_click_callback()

    def _on_input_focus(self, event: tk.Event) -> None:
        """Clear placeholder text when input is focused."""
        if self._input_var.get() == "Type a command...":
            self._input_entry.delete(0, tk.END)
            self._input_entry.config(fg=PRIMARY)

    def _on_input_blur(self, event: tk.Event) -> None:
        """Restore placeholder text when input loses focus."""
        if not self._input_var.get().strip():
            self._input_entry.insert(0, "Type a command...")
            self._input_entry.config(fg=TEXT_DIM)

    def _on_text_submit(self, event) -> None:
        """Handle text command submission."""
        text = self._input_var.get().strip()
        if not text or text == "Type a command...":
            return
        self._input_entry.delete(0, tk.END)
        self.add_conversation("You", text)
        if self._on_text_command_callback:
            import threading
            threading.Thread(
                target=self._on_text_command_callback,
                args=(text,),
                daemon=True,
            ).start()

    def _on_close(self) -> None:
        """Handle window close."""
        self._running = False
        self.destroy()

    # ─── Keyboard Shortcuts ─────────────────────────────

    def _toggle_fullscreen(self, event=None) -> None:
        """Toggle fullscreen mode."""
        self._is_fullscreen = not self._is_fullscreen
        self.attributes('-fullscreen', self._is_fullscreen)
        if not self._is_fullscreen:
            self.geometry("1280x720")
        self.show_notification(
            "Fullscreen ON" if self._is_fullscreen else "Windowed mode",
            "info",
        )

    def _toggle_mini_mode(self, event=None) -> None:
        """Toggle mini floating mode (small window with just reactor + input)."""
        self._is_mini = not self._is_mini
        if self._is_mini:
            self.attributes('-fullscreen', False)
            self.geometry("400x200")
            self.attributes('-topmost', True)
            self.show_notification("Mini mode — F10 to expand", "info")
        else:
            self.attributes('-fullscreen', True)
            self.attributes('-topmost', self._is_on_top)
            self._is_fullscreen = True
            self.show_notification("Full HUD restored", "info")

    def _toggle_always_on_top(self, event=None) -> None:
        """Toggle always-on-top."""
        self._is_on_top = not self._is_on_top
        self.attributes('-topmost', self._is_on_top)
        self.show_notification(
            "Pinned on top" if self._is_on_top else "Unpinned",
            "info",
        )

    # ─── Animation Loop ─────────────────────────────────

    def start_animation(self) -> None:
        """Start the animation loop."""
        self._animate()

    def _animate(self) -> None:
        """Main animation frame — updates and redraws all components."""
        if not self._running:
            return

        now = time.time()
        dt = now - self.last_time
        self.last_time = now

        # Update components
        self.arc_reactor.update(dt)
        self.radar.update(dt)
        self.particles.update(dt)

        # Draw everything
        try:
            self.particles.draw()  # Draw particles first (background layer)
            self.top_bar.draw()
            self.arc_reactor.draw()
            self.waveform.draw()
            self.system_panel.draw()
            self.log_panel.draw()
            self.radar.draw()
            self._draw_notifications()
            self._draw_conversation()
        except tk.TclError:
            return  # Window was closed

        # Schedule next frame
        delay = max(1, int(1000 / self.fps_target))
        try:
            self.after(delay, self._animate)
        except tk.TclError:
            pass

    # ─── Public Update Methods ──────────────────────────

    def update_state(self, state: str) -> None:
        """Update the HUD state (idle, listening, processing, speaking)."""
        self.arc_reactor.set_state(state)
        self.waveform.set_active(state in ("listening", "active_listening"))
        self.particles.set_state(state)
        status_map = {
            "idle": "SYSTEM ONLINE — STANDBY",
            "wake_listening": "SYSTEM ONLINE — STANDBY",
            "listening": "● ACTIVE LISTENING",
            "active_listening": "● ACTIVE LISTENING",
            "processing": "⚡ PROCESSING COMMAND",
            "speaking": "◆ RESPONDING",
            "sleeping": "○ SLEEP MODE",
        }
        self.top_bar.set_status(status_map.get(state, "SYSTEM ONLINE"))

    def update_waveform(self, levels: list[float]) -> None:
        """Update waveform visualization with audio levels."""
        self.waveform.update_levels(levels)

    def update_system_stats(self, stats: dict) -> None:
        """Update system diagnostics panel."""
        self.system_panel.update_stats(stats)

    def update_command_log(self, entries: list[dict]) -> None:
        """Update the activity log panel."""
        self.log_panel.update_log(entries)

    def add_radar_blip(self, angle: Optional[int] = None) -> None:
        """Add a blip to the radar display."""
        if angle is None:
            angle = random.randint(0, 359)
        self.radar.add_blip(angle)

    # ─── Notification System ────────────────────────────

    def show_notification(self, message: str, level: str = "info") -> None:
        """
        Show a toast notification on the HUD.

        Args:
            message: Notification text.
            level: "info", "success", "warning", or "error".
        """
        color_map = {
            "info": PRIMARY,
            "success": ACCENT_GREEN,
            "warning": "#ff9000",
            "error": "#ff0040",
        }
        self._notifications.append({
            "message": message,
            "color": color_map.get(level, PRIMARY),
            "time": time.time(),
            "duration": 4.0,
        })

    def _draw_notifications(self) -> None:
        """Draw active notifications (top-right toast style)."""
        for item in self._notification_items:
            self.canvas.delete(item)
        self._notification_items.clear()

        now = time.time()
        active = [n for n in self._notifications if now - n["time"] < n["duration"]]
        x = self.w - 320
        y = 120

        for notif in active:
            elapsed = now - notif["time"]
            alpha = min(1.0, 1.0 - (elapsed / notif["duration"]) * 0.3)
            color = notif["color"]
            msg = notif["message"]
            if len(msg) > 40:
                msg = msg[:37] + "..."

            item = self.canvas.create_text(
                x, y, text=f"▸ {msg}",
                fill=color, font=("Consolas", 9),
                anchor="nw",
            )
            self._notification_items.append(item)
            y += 22

    # ─── Conversation Display ───────────────────────────

    def add_conversation(self, speaker: str, text: str) -> None:
        """Add a conversation entry to the display."""
        self._conversation.append({
            "speaker": speaker,
            "text": text,
            "time": time.time(),
        })

    def _draw_conversation(self) -> None:
        """Draw recent conversation below the waveform."""
        for item in self._conversation_items:
            self.canvas.delete(item)
        self._conversation_items.clear()

        if not self._conversation:
            return

        cx = self.w // 2
        base_y = self.waveform.cy + 50
        entries = list(self._conversation)[-4:]

        for i, entry in enumerate(entries):
            y = base_y + i * 22
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

            item = self.canvas.create_text(
                cx, y, text=f"{prefix} {text}",
                fill=color, font=("Consolas", 9),
            )
            self._conversation_items.append(item)
