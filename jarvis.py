"""
J.A.R.V.I.S. 2.0 — Just A Rather Very Intelligent System
Iron Man-inspired AI Desktop Assistant

Launch: python jarvis.py

Features:
- Wake word: "Hey Jarvis"
- Fullscreen Iron Man HUD with arc reactor, waveform, radar
- Voice commands: open apps, search web, play YouTube, Wikipedia, etc.
- System control: shutdown, restart, lock, volume, screenshot
- AI conversation via Google Gemini
- System monitoring: CPU, RAM, Battery, Network
- Routines, schedules, and custom commands
"""
import sys
import os
import threading
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    print("=" * 50)
    print("  J.A.R.V.I.S. 2.0")
    print("  Just A Rather Very Intelligent System")
    print("=" * 50)
    print()

    # ─── Phase 1: Initialize core systems ────────────────
    print("[Boot] Loading brain...")
    from core.brain import load_brain
    load_brain()

    print("[Boot] Starting speaker...")
    from core.speaker import start_speaker, speak
    start_speaker()

    print("[Boot] Starting system monitor...")
    from core.system_info import start_monitor, get_stats
    start_monitor()

    print("[Boot] Initializing AI engine...")
    from core.ai_engine import init_ai
    init_ai()

    # ─── Phase 2: Initialize executor ────────────────────
    from core.executor import execute, get_command_log

    # ─── Phase 3: Initialize listener ────────────────────
    print("[Boot] Starting voice listener...")
    from core.listener import (
        start_listener, set_on_command, set_on_state_change,
        manual_activate, get_waveform_levels, terminate_event
    )
    set_on_command(execute)

    # ─── Phase 4: Initialize scheduler ───────────────────
    print("[Boot] Starting scheduler...")
    from core.scheduler import start_scheduler, register_hotkeys
    start_scheduler(execute)
    register_hotkeys(execute)

    # ─── Phase 5: Launch HUD ─────────────────────────────
    print("[Boot] Launching HUD...")
    from ui.hud import JarvisHUD

    hud = JarvisHUD()

    # Connect listener state changes to HUD
    def on_state_change(state):
        try:
            hud.update_state(state)
            if state in ("active_listening", "processing"):
                hud.add_radar_blip()
        except Exception:
            pass

    set_on_state_change(on_state_change)

    # Connect click to manual activation
    hud.set_on_click(manual_activate)

    # ─── Phase 6: Start background update threads ────────

    def data_update_loop():
        """Feed real-time data into the HUD."""
        while not terminate_event.is_set():
            try:
                # Update system stats
                stats = get_stats()
                hud.update_system_stats(stats)

                # Update waveform levels
                levels = get_waveform_levels()
                hud.update_waveform(levels)

                # Update command log
                log = get_command_log()
                hud.update_command_log(log)
            except Exception:
                pass
            time.sleep(0.1)

    threading.Thread(target=data_update_loop, daemon=True, name="DataUpdate").start()

    # ─── Phase 7: Start listening & boot message ─────────
    start_listener()

    # Boot complete message
    speak("Jarvis is online. All systems operational.", block=False)
    print()
    print("[Boot] ✓ All systems go. Say 'Hey Jarvis' or click the screen.")
    print("[Boot] Press ESC to exit.")
    print()

    # ─── Phase 8: Run the GUI event loop ─────────────────
    hud.start_animation()

    try:
        hud.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[Shutdown] Cleaning up...")
        terminate_event.set()
        from core.listener import stop_listener
        from core.system_info import stop_monitor
        from core.speaker import stop_speaker
        from core.brain import save_brain
        stop_listener()
        stop_monitor()
        save_brain()
        stop_speaker()
        print("[Shutdown] Goodbye.")


if __name__ == "__main__":
    main()
