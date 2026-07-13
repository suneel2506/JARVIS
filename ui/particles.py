"""
ui/particles.py — Holographic particle system for J.A.R.V.I.S. HUD.

Floating neon particles that drift across the background, creating
a living, breathing holographic atmosphere. Particles respond to
state changes: speed up during processing, glow brighter during speaking.
"""
import random
import math

from ui.colors import PRIMARY, PRIMARY_DIM, PRIMARY_DARK, SECONDARY, dim_color


class Particle:
    """A single floating holographic particle."""

    __slots__ = ('x', 'y', 'vx', 'vy', 'size', 'alpha', 'life', 'max_life', 'color')

    def __init__(self, x: float, y: float, screen_w: int, screen_h: int):
        self.x = x
        self.y = y
        self.vx = random.uniform(-0.3, 0.3)
        self.vy = random.uniform(-0.2, -0.05)
        self.size = random.uniform(1, 3)
        self.alpha = random.uniform(0.3, 0.8)
        self.max_life = random.uniform(8.0, 20.0)
        self.life = self.max_life
        self.color = random.choice([PRIMARY_DIM, PRIMARY_DARK, SECONDARY])


class ParticleSystem:
    """
    Manages a field of floating holographic particles on a tkinter canvas.

    Particles drift upward slowly, fade over time, and respawn at random
    positions. The system responds to state changes by adjusting speed
    and particle density.
    """

    def __init__(self, canvas, screen_w: int, screen_h: int, max_particles: int = 40):
        self.canvas = canvas
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.max_particles = max_particles
        self.particles: list[Particle] = []
        self.items: list[int] = []
        self.speed_multiplier = 1.0
        self._state = "idle"

        # Initialize particles
        for _ in range(max_particles):
            self._spawn_particle()

    def _spawn_particle(self) -> None:
        """Spawn a new particle at a random position."""
        x = random.uniform(0, self.screen_w)
        y = random.uniform(0, self.screen_h)
        self.particles.append(Particle(x, y, self.screen_w, self.screen_h))

    def set_state(self, state: str) -> None:
        """Adjust particle behavior based on system state."""
        self._state = state
        if state in ("processing", "active_listening"):
            self.speed_multiplier = 2.5
        elif state == "speaking":
            self.speed_multiplier = 1.5
        else:
            self.speed_multiplier = 1.0

    def update(self, dt: float) -> None:
        """Update all particle positions and lifetimes."""
        to_remove = []
        for p in self.particles:
            p.x += p.vx * self.speed_multiplier * dt * 60
            p.y += p.vy * self.speed_multiplier * dt * 60
            p.life -= dt

            # Fade out as life decreases
            life_ratio = max(0, p.life / p.max_life)
            p.alpha = life_ratio * 0.6

            if p.life <= 0 or p.x < -10 or p.x > self.screen_w + 10 or p.y < -10:
                to_remove.append(p)

        for p in to_remove:
            self.particles.remove(p)

        # Respawn to maintain count
        while len(self.particles) < self.max_particles:
            x = random.uniform(0, self.screen_w)
            y = random.uniform(self.screen_h * 0.3, self.screen_h)
            self.particles.append(Particle(x, y, self.screen_w, self.screen_h))

    def draw(self) -> None:
        """Draw all particles on the canvas."""
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

        for p in self.particles:
            if p.alpha < 0.1:
                continue

            # Draw as small circles with dim glow
            half = p.size
            color = dim_color(p.color, p.alpha)
            item = self.canvas.create_oval(
                p.x - half, p.y - half,
                p.x + half, p.y + half,
                fill=color, outline="",
            )
            self.items.append(item)

            # Glow effect for larger particles
            if p.size > 2 and p.alpha > 0.3:
                glow_size = p.size * 2
                glow_color = dim_color(p.color, p.alpha * 0.3)
                item = self.canvas.create_oval(
                    p.x - glow_size, p.y - glow_size,
                    p.x + glow_size, p.y + glow_size,
                    fill=glow_color, outline="",
                )
                self.items.append(item)
