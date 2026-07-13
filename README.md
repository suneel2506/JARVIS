# J.A.R.V.I.S.

**Just A Rather Very Intelligent System** — A professional desktop AI assistant inspired by Iron Man.

> "Good evening, sir. All systems are online and ready."

---

## Features

### 🎤 Voice Interaction
- **Wake-word activation** — Say "Hey Jarvis" to activate
- **Offline recognition** via Vosk (no internet needed for basic commands)
- **Google Speech API** fallback for accurate online recognition
- **Click-to-talk** — Click anywhere on the HUD to activate

### 💬 AI Conversation
- **Google Gemini** integration for natural language understanding
- Contextual, witty responses in JARVIS character
- Memory-aware AI — JARVIS remembers facts about you

### 🧠 Long-Term Memory
- **Remember facts** — "Remember my college is MIT"
- **User preferences** — "I prefer dark mode"
- **Aliases** — "Call me Boss"
- **Notes** — "Note: buy groceries tomorrow"
- **Smart recall** — "Where do I study?" pulls from stored facts

### 🖥️ Iron Man HUD
- Fullscreen animated canvas at 30fps
- **Arc reactor** with state-driven animations (idle, listening, processing, speaking)
- **Voice waveform** visualization
- **Radar sweep** with command blips
- **System diagnostics** — CPU, RAM, Battery, Disk, Network, Mic
- **Activity log** — Real-time command history
- **Text input** — Type commands as an alternative to voice
- **Toast notifications** — Visual feedback for system events

### ⚡ System Control
- Open/close 57+ applications by name
- Shutdown, restart, lock, sleep, log off
- Volume and media playback control
- Screenshot, typing, and key press automation
- Brightness control

### 📁 File Management
- Create folders, rename/delete/move files
- Open files in default app
- List desktop contents

### 🌐 Web & Browser
- Google, YouTube, GitHub, StackOverflow, Wikipedia search
- Open 25+ named websites by voice
- Direct URL navigation

### 🔧 Customization
- User-taught custom commands
- Scheduled routines with daily repeat
- Global hotkey bindings
- All settings in `config/settings.json`

---

## Architecture

```
jarvis.py                  ← Single entry point
├── config/
│   ├── config.py          ← Central configuration (loads settings.json + env vars)
│   └── settings.json      ← All tunable parameters
├── core/
│   ├── ai_engine.py       ← Gemini conversation engine
│   ├── brain.py           ← Persistent data (commands, routines, schedules)
│   ├── executor.py        ← 15-step command router with priority chain
│   ├── listener.py        ← Wake-word + command capture (Vosk + Google)
│   ├── logger.py          ← Structured logging (console + file + conversations)
│   ├── memory.py          ← Long-term memory (facts, preferences, notes)
│   ├── mic.py             ← Custom sounddevice microphone
│   ├── scheduler.py       ← Scheduled routines and hotkeys
│   ├── speaker.py         ← Thread-safe TTS with speaking callbacks
│   └── system_info.py     ← Real-time system monitoring
├── commands/
│   ├── ai.py              ← AI + memory commands
│   ├── apps.py            ← Application launcher (57 apps)
│   ├── automation.py      ← Screenshots, typing, hotkeys
│   ├── browser.py         ← Browser navigation + web searches
│   ├── custom.py          ← User-taught commands
│   ├── files.py           ← File/folder management
│   ├── media.py           ← Media playback + volume
│   ├── smart.py           ← Time, date, weather, jokes, system status
│   ├── system.py          ← Power management + system queries
│   └── web.py             ← General web search fallback
├── ui/
│   ├── hud.py             ← Main HUD compositor
│   ├── arc_reactor.py     ← Animated arc reactor
│   ├── colors.py          ← Iron Man cyan theme
│   ├── top_bar.py         ← Clock, date, status display
│   ├── side_panels.py     ← Diagnostics + activity log
│   ├── waveform.py        ← Voice visualization
│   └── radar.py           ← Radar sweep animation
├── memory/
│   └── brain.json         ← Persistent memory store
├── model/
│   └── vosk-model-small-en-us-0.15/  ← Offline speech model
└── logs/                  ← Rotating log files
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Windows 10/11
- Microphone

### Installation

```bash
# Clone the repository
git clone https://github.com/suneel2506/JARVIS.git
cd JARVIS

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy environment template
copy .env.example .env

# Edit .env and add your API keys
# GEMINI_API_KEY=your_key_here
```

### Vosk Model

Download the [Vosk small English model](https://alphacephei.com/vosk/models) and extract to:
```
model/vosk-model-small-en-us-0.15/
```

### Run

```bash
python jarvis.py
```

---

## Voice Commands

| Category | Examples |
|----------|---------|
| **Apps** | "Open Chrome", "Launch VS Code", "Close Notepad" |
| **Browser** | "Search Google for Python", "Open GitHub", "YouTube search AI" |
| **Media** | "Play Believer on YouTube", "Pause", "Volume up", "Next track" |
| **System** | "Shutdown", "Lock PC", "Battery status", "CPU usage" |
| **Files** | "Create folder Projects", "Delete test.txt", "List desktop" |
| **Memory** | "Remember my college is MIT", "What's my college?", "Call me Boss" |
| **Smart** | "What time is it?", "Tell me a joke", "Weather in London" |
| **AI** | "Tell me about quantum computing", "Explain recursion" |
| **Notes** | "Note: buy groceries", "Show notes", "Clear notes" |
| **Automation** | "Take screenshot", "Type hello world", "Press ctrl+c" |

---

## License

MIT License

---

*"I am J.A.R.V.I.S. — your personal AI assistant, sir."*
