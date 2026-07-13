"""
ui/colors.py — Iron Man HUD color theme and glow utilities.
"""

# ─── Iron Man JARVIS Cyan Theme ─────────────────────────
BG              = "#05080d"       # Deep space black
BG_PANEL        = "#0a1020"       # Panel background
BG_PANEL_LIGHT  = "#0d1830"       # Lighter panel

PRIMARY         = "#00eaff"       # Neon cyan
PRIMARY_DIM     = "#005f6a"       # Dim cyan
PRIMARY_DARK    = "#003040"       # Very dim cyan

SECONDARY       = "#0080ff"       # Electric blue
ACCENT_GREEN    = "#00ff88"       # Green accent (success)
ACCENT_ORANGE   = "#ff9000"       # Orange (warning)
ACCENT_RED      = "#ff0040"       # Red (danger/critical)

TEXT            = "#c0f0ff"       # Light cyan text
TEXT_DIM        = "#406070"       # Dim text
TEXT_BRIGHT     = "#ffffff"       # Bright white

REACTOR_CORE    = "#80ffff"       # Arc reactor inner glow
REACTOR_RING    = "#00c8e0"       # Arc reactor ring color
REACTOR_OUTER   = "#004060"       # Arc reactor outer ring

WAVEFORM        = "#00d4ff"       # Waveform bars
WAVEFORM_DIM    = "#003050"       # Waveform dim

RADAR           = "#00eaff"       # Radar sweep
RADAR_DIM       = "#002030"       # Radar background

BORDER          = "#0a3040"       # Panel borders
BORDER_BRIGHT   = "#00a0c0"       # Bright borders

GRID            = "#081520"       # Grid lines on panels


def hex_to_rgb(hex_color):
    """Convert hex color to (r, g, b) tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    """Convert (r, g, b) to hex color string."""
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def lerp_color(color1, color2, t):
    """Linearly interpolate between two hex colors. t=0→color1, t=1→color2."""
    r1, g1, b1 = hex_to_rgb(color1)
    r2, g2, b2 = hex_to_rgb(color2)
    t = max(0, min(1, t))
    r = r1 + (r2 - r1) * t
    g = g1 + (g2 - g1) * t
    b = b1 + (b2 - b1) * t
    return rgb_to_hex(r, g, b)


def dim_color(hex_color, factor=0.5):
    """Dim a color by a factor (0=black, 1=original)."""
    r, g, b = hex_to_rgb(hex_color)
    return rgb_to_hex(r * factor, g * factor, b * factor)


def brighten_color(hex_color, factor=1.3):
    """Brighten a color by a factor."""
    r, g, b = hex_to_rgb(hex_color)
    return rgb_to_hex(min(255, r * factor), min(255, g * factor), min(255, b * factor))
