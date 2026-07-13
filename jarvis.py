"""
jarvis.py — Main entry point for J.A.R.V.I.S.

Just A Rather Very Intelligent System — a professional desktop AI assistant.

This module orchestrates all subsystems:
- Voice listener (wake-word detection + command capture)
- Text-to-speech engine
- AI conversation engine (Gemini)
- System monitoring
- Scheduled routines and hotkeys
- Iron Man HUD (fullscreen tkinter canvas)

Usage:
    python jarvis.py
"""
import sys
import time
import threading

from core.logger import get_logger

log = get_logger("jarvis")


# ─── Startup Sequence ───────────────────────────────────

def _startup_phase(hud, speak_fn):
    """Run the JARVIS boot sequence with HUD and voice."""
    phases = [
        ("INITIALIZING CORE SYSTEMS...", "idle", 0.8),
        ("LOADING VOICE ENGINE...", "idle", 0.6),
        ("CONNECTING AI ENGINE...", "processing", 0.8),
        ("CALIBRATING SENSORS...", "processing", 0.6),
        ("ALL SYSTEMS ONLINE", "idle", 0.5),
    ]
    for status, state, delay in phases:
        try:
            hud.top_bar.set_status(status)
            hud.update_state(state)
            hud.show_notification(status, "info")
        except Exception:
            pass
        time.sleep(delay)

    try:
        hud.update_state("idle")
    except Exception:
        pass

    speak_fn("J.A.R.V.I.S. online. All systems operational. How can I help you, sir?", block=False)
    log.info("Startup sequence complete")


def main():
    """Main application entry point."""
    log.info("=" * 60)
    log.info("J.A.R.V.I.S. v2.0 — Starting up...")
    log.info("=" * 60)

    # ─── Initialize Core ────────────────────────────────
    from core.speaker import speak, start_speaker, set_on_speaking
    from core.listener import (
        start_listener, stop_listener, set_on_command,
        set_on_state_change, get_waveform_levels, manual_activate,
    )
    from core.executor import execute, get_command_log
    from core.system_info import start_monitor, get_stats
    from core.scheduler import start_scheduler, register_hotkeys
    from core.ai_engine import init_ai
    from core.brain import load_brain

    # Load persistent data
    load_brain()

    # Initialize AI
    init_ai()

    # Start speaker
    start_speaker()

    # ─── Build HUD ──────────────────────────────────────
    from ui.hud import JarvisHUD

    hud = JarvisHUD()
    log.info("HUD initialized (%dx%d)", hud.w, hud.h)

    # ─── Wire Callbacks ─────────────────────────────────

    def on_state_change(state):
        """Sync listener state → HUD."""
        try:
            hud.update_state(state)
        except Exception:
            pass

    def on_command(cmd):
        """Process a voice command."""
        hud.add_conversation("You", cmd)
        hud.add_radar_blip()
        result = execute(cmd)
        return result

    def on_text_command(text):
        """Process a typed command."""
        result = execute(text)
        if result == "exit":
            try:
                stop_listener()
                hud._on_close()
            except Exception:
                pass

    def on_speaking(is_speaking):
        """Sync speaker state → HUD."""
        try:
            if is_speaking:
                hud.update_state("speaking")
            else:
                hud.update_state("wake_listening")
        except Exception:
            pass

    def on_click():
        """Handle click-to-activate."""
        manual_activate()

    set_on_command(on_command)
    set_on_state_change(on_state_change)
    set_on_speaking(on_speaking)
    hud.set_on_click(on_click)
    hud.set_on_text_command(on_text_command)

    # ─── Start Background Services ──────────────────────
    start_monitor()
    start_scheduler(execute)
    register_hotkeys(execute)

    # ─── HUD Data Refresh Loop ──────────────────────────
    def _hud_data_loop():
        """Background thread: refreshes HUD data every second."""
        while True:
            try:
                stats = get_stats()
                from core.listener import get_state
                stats["mic_state"] = get_state()
                hud.update_system_stats(stats)
                hud.update_waveform(get_waveform_levels())
                hud.update_command_log(get_command_log())
            except Exception:
                pass
            time.sleep(1)

    threading.Thread(target=_hud_data_loop, daemon=True, name="HUDData").start()

    # ─── Startup Sequence ───────────────────────────────
    threading.Thread(
        target=_startup_phase, args=(hud, speak),
        daemon=True, name="Startup",
    ).start()

    # Start voice listener
    start_listener()
    log.info("Voice listener started")

    # ─── Start Animation + Main Loop ────────────────────
    hud.start_animation()
    log.info("HUD animation started — entering main loop")

    try:
        hud.mainloop()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        log.info("Shutting down...")
        stop_listener()
        log.info("J.A.R.V.I.S. offline")


if __name__ == "__main__":
    main()
