"""
Fireboy and Watergirl - Starter Game
=====================================
A two-player co-operative platformer.

Controls:
  Fireboy   → Arrow Keys  (LEFT / RIGHT to move, UP to jump)
  Watergirl → WASD        (A / D to move,         W to jump)

Design overview
---------------
The game is structured around four main concerns:

  1. Rendering  – Background, Platform, Jewel, and Character subclasses each
                  own their own draw() method so visual code stays local to
                  the thing being drawn.

  2. Physics    – A lightweight Euler-integration loop lives in Character:
                  gravity accumulates into vy each frame; move() separates
                  horizontal and vertical resolution so corner collisions
                  don't cause the character to get stuck.

  3. Hazards    – Platforms carry a "kind" tag ("normal" | "lava" | "water").
                  Hazard death is checked every frame via check_hazards(),
                  which tests direct overlap — not just landing — so walking
                  into a pool is caught regardless of movement direction.

  4. Jewels     – Each jewel has a "kind" tag; _can_collect() in each
                  Character subclass gates collection so only the right
                  player can pick up each colour.

  5. Doors      – Each character has a matching exit door.  Both characters
                  must stand at their respective doors simultaneously to
                  complete the level — just like the original game.

Requirements: pip install pygame
"""

import pygame
import sys
import math
import random
import json
import os

pygame.init()

# ── Constants ──────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 900, 600
FPS           = 60
GRAVITY       = 0.55   # pixels / frame² — kept low for a floaty, game-like feel
JUMP_SPEED    = -13    # negative because pygame's y-axis points downward
MOVE_SPEED    = 4      # horizontal pixels per frame

# Colour palette
# Keeping colours as named constants means we never hard-code magic numbers
# inside draw methods, and recolouring the game only requires changing this block.
SKY            = (15, 10, 30)
GROUND_TOP     = (60, 40, 20)
GROUND_DARK    = (40, 25, 10)
PLATFORM_TOP   = (80, 55, 30)
PLATFORM_SIDE  = (55, 35, 15)
LAVA_A         = (220, 60, 10)
LAVA_B         = (255, 130, 0)
WATER_A        = (20, 80, 200)
WATER_B        = (80, 180, 255)

# Each jewel type gets a three-stop gradient: outer glow → mid → bright core
JEWEL_FIRE_COL  = [(255, 80, 0),   (255, 160, 40),  (255, 220, 80)]
JEWEL_WATER_COL = [(0, 120, 255),  (80, 200, 255),  (180, 240, 255)]
JEWEL_GREEN_COL = [(0, 200, 80),   (80, 255, 150),  (180, 255, 220)]

# ── Global pygame objects ───────────────────────────────────────────────────────
screen     = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Fireboy & Watergirl")
clock      = pygame.time.Clock()
font_big   = pygame.font.SysFont("Arial", 28, bold=True)
font_small = pygame.font.SysFont("Arial", 18)
font_title = pygame.font.SysFont("Arial", 52, bold=True)
font_menu  = pygame.font.SysFont("Arial", 24, bold=True)


# ── Leaderboard persistence ────────────────────────────────────────────────────

SCORES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best_times.json")
MAX_RECORDS = 10


def _rank_key(record):
    """Sort key: highest score first, fastest time breaks ties."""
    return (-record["score"], record["time"])


def load_records():
    """Load the ranked list of {score, time} records from disk."""
    if os.path.exists(SCORES_FILE):
        try:
            with open(SCORES_FILE, "r") as f:
                data = json.load(f)
            if data and isinstance(data[0], (int, float)):
                data = [{"score": 0, "time": t} for t in data]
            return sorted(data, key=_rank_key)[:MAX_RECORDS]
        except (json.JSONDecodeError, TypeError, KeyError):
            return []
    return []


def save_records(records):
    """Write the ranked records list to disk."""
    with open(SCORES_FILE, "w") as f:
        json.dump(sorted(records, key=_rank_key)[:MAX_RECORDS], f)


def is_new_high(score, time, records):
    """True if this run would rank #1 overall."""
    if not records:
        return True
    best = records[0]
    return score > best["score"] or (score == best["score"] and time < best["time"])


def format_time(seconds):
    """Format a float seconds value as M:SS.d  (e.g. 1:04.3)."""
    mins = int(seconds) // 60
    secs = seconds - mins * 60
    return f"{mins}:{secs:04.1f}"


# ── Helpers ────────────────────────────────────────────────────────────────────

def lerp_color(a, b, t):
    """
    Linearly interpolate between two RGB colours.
    t=0 → colour a,  t=1 → colour b.
    Used for animated lava/water shimmer effects.
    """
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_rounded_rect(surf, color, rect, radius=8):
    """Thin wrapper around pygame's border_radius argument for readability."""
    pygame.draw.rect(surf, color, rect, border_radius=radius)


# ══════════════════════════════════════════════════════════════════════════════
# ANIMATED BACKGROUND
# ══════════════════════════════════════════════════════════════════════════════

class Background:
    """
    Draws and animates the cave environment behind the gameplay elements.

    Design choice — everything purely decorative lives here so the game-logic
    classes (Character, Platform, Jewel) stay focused on mechanics, not
    atmosphere.

    Elements:
      - Vertical gradient sky (drawn line-by-line; cheap at 600px tall)
      - Flickering torch glows on the side walls
      - Static stalactites / stalagmites for cave feel
      - Rising dust particles with a gentle sine drift
    """

    def __init__(self):
        self.tick = 0

        # Pre-generate random stalactite / stalagmite positions once.
        # (x position, y start, height) tuples.
        self.stalactites = [
            (random.randint(0, WIDTH), random.randint(20, 80), random.randint(15, 40))
            for _ in range(14)
        ]
        self.stalagmites = [
            (random.randint(0, WIDTH), random.randint(520, 560), random.randint(15, 35))
            for _ in range(12)
        ]

        # Dust particles — each is a small dict so we can mutate fields in-place.
        self.dust = [
            {
                "x":     random.randint(0, WIDTH),
                "y":     random.randint(0, HEIGHT),
                "r":     random.uniform(0.8, 2.5),
                "speed": random.uniform(0.2, 0.7),
                "alpha": random.randint(60, 160),
            }
            for _ in range(60)
        ]

    def update(self):
        """Advance animation tick and move dust particles upward."""
        self.tick += 1
        for p in self.dust:
            p["y"] -= p["speed"]
            # Gentle horizontal sine wobble keyed to the particle's y position
            p["x"] += math.sin(self.tick * 0.02 + p["y"]) * 0.3
            # Wrap particles that drift off the top back to the bottom
            if p["y"] < -4:
                p["y"] = HEIGHT + 4
                p["x"] = random.randint(0, WIDTH)

    def draw(self, surf):
        # ── Sky gradient (top → bottom, dark purple to dark brown) ──────────
        for y in range(HEIGHT):
            t = y / HEIGHT
            c = lerp_color((20, 12, 45), (45, 25, 10), t)
            pygame.draw.line(surf, c, (0, y), (WIDTH, y))

        # ── Torch glows — two per side wall ─────────────────────────────────
        # flicker is a sine wave in [0.6, 1.0] so the glow pulses naturally
        for tx, ty in [(60, 150), (60, 350), (WIDTH - 60, 150), (WIDTH - 60, 350)]:
            flicker = math.sin(self.tick * 0.15) * 0.2 + 0.8
            # Three concentric alpha circles give a soft glow falloff
            for r, a in [(55, 25), (35, 50), (18, 90)]:
                s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                color = (255, int(160 * flicker), 20, int(a * flicker))
                pygame.draw.circle(s, color, (r, r), r)
                surf.blit(s, (tx - r, ty - r))
            pygame.draw.circle(surf, (255, 220, 100), (tx, ty), 5)

        # ── Stalactites (hang from ceiling) ─────────────────────────────────
        for x, y, h in self.stalactites:
            sw = max(4, h // 2)
            pts = [(x - sw, y), (x + sw, y), (x, y + h)]
            pygame.draw.polygon(surf, (50, 35, 20), pts)
            # Inner highlight to give faint 3-D faceting
            pygame.draw.polygon(surf, (70, 50, 30),
                                 [(x - sw + 2, y), (x, y + h - 4), (x + sw - 2, y)])

        # ── Stalagmites (rise from floor) ────────────────────────────────────
        for x, y, h in self.stalagmites:
            sw = max(4, h // 2)
            pts = [(x - sw, y), (x + sw, y), (x, y - h)]
            pygame.draw.polygon(surf, (50, 35, 20), pts)
            pygame.draw.polygon(surf, (70, 50, 30),
                                 [(x - sw + 2, y), (x, y - h + 4), (x + sw - 2, y)])

        # ── Dust particles ───────────────────────────────────────────────────
        # Drawn onto a dedicated SRCALPHA surface so each particle can have
        # its own alpha without affecting the background underneath.
        dust_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for p in self.dust:
            pygame.draw.circle(
                dust_surf,
                (200, 190, 170, p["alpha"]),
                (int(p["x"]), int(p["y"])),
                int(p["r"]),
            )
        surf.blit(dust_surf, (0, 0))


# ══════════════════════════════════════════════════════════════════════════════
# PLATFORM
# ══════════════════════════════════════════════════════════════════════════════

class Platform:
    """
    A rectangular surface the characters can stand on.

    The 'kind' tag drives both visual style and hazard behaviour:
      "normal" – safe for both characters
      "lava"   – kills Watergirl on contact
      "water"  – kills Fireboy on contact

    Design choice: visuals and physics data are bundled in Platform rather
    than kept in separate lists because every collision check and every draw
    call needs both the rect and the kind together.
    """

    def __init__(self, x, y, w, h=18, kind="normal"):
        self.rect = pygame.Rect(x, y, w, h)
        self.kind = kind   # "normal" | "lava" | "water"
        self.tick = 0      # local animation timer

    def update(self):
        """Advance the per-platform animation clock."""
        self.tick += 1

    def draw(self, surf):
        r = self.rect

        if self.kind == "lava":
            # Colour cycles between LAVA_A and LAVA_B using a sine wave
            t = (math.sin(self.tick * 0.08) + 1) / 2
            top_col = lerp_color(LAVA_A, LAVA_B, t)
            draw_rounded_rect(surf, (80, 20, 0), r.inflate(0, 4), 6)  # dark base
            draw_rounded_rect(surf, top_col, r, 6)
            # Animated lava bubbles — three evenly-spaced, sine-offset dots
            for i in range(3):
                bx = r.x + 12 + i * (r.w // 3)
                by = r.y + int(math.sin(self.tick * 0.12 + i * 2) * 3)
                pygame.draw.circle(surf, LAVA_B, (bx, by), 4)

        elif self.kind == "water":
            t = (math.sin(self.tick * 0.06) + 1) / 2
            top_col = lerp_color(WATER_A, WATER_B, t)
            draw_rounded_rect(surf, (10, 40, 120), r.inflate(0, 4), 6)
            draw_rounded_rect(surf, top_col, r, 6)
            for i in range(3):
                bx = r.x + 12 + i * (r.w // 3)
                by = r.y + int(math.sin(self.tick * 0.10 + i * 1.5) * 3)
                pygame.draw.circle(surf, WATER_B, (bx, by), 4)

        else:
            # Normal stone/dirt platform: a darker inflated shadow rect beneath,
            # the main surface on top, plus a mossy highlight stripe.
            draw_rounded_rect(surf, PLATFORM_SIDE, r.inflate(0, 6), 6)
            draw_rounded_rect(surf, PLATFORM_TOP, r, 6)
            pygame.draw.rect(surf, (90, 65, 38),
                             (r.x + 4, r.y + 3, r.w - 8, 4), border_radius=3)


# ══════════════════════════════════════════════════════════════════════════════
# JEWEL  (animated spinning gem)
# ══════════════════════════════════════════════════════════════════════════════

class Jewel:
    """
    A collectible gem that bobs up and down and spins while uncollected,
    then floats upward and fades out once picked up.

    kind:
      "fire"  – only Fireboy can collect (fire + green jewels score for him)
      "water" – only Watergirl can collect
      "green" – either character can collect

    Design choice: keeping the collect animation inside the jewel itself
    (rather than spawning a separate particle) keeps the object count low and
    lets the jewel list simply filter out dead entries each frame.
    """

    SIZE   = 16   # half-width of the diamond hitbox
    BOUNCE = 6    # vertical bob amplitude in pixels

    def __init__(self, x, y, kind="fire"):
        self.x      = x
        self.y      = y
        self.base_y = y          # original y; bob is relative to this
        self.kind   = kind
        self.tick   = random.randint(0, 60)  # stagger phase so jewels don't all bob in sync
        self.collected = False
        self.fade      = 255    # alpha; counts down to 0 after collection

        # Pick the colour gradient that matches the jewel type
        if kind == "fire":
            self.colors = JEWEL_FIRE_COL
        elif kind == "water":
            self.colors = JEWEL_WATER_COL
        else:
            self.colors = JEWEL_GREEN_COL

    @property
    def rect(self):
        """Axis-aligned rect used for collision detection."""
        s = self.SIZE
        return pygame.Rect(self.x - s // 2, int(self.y) - s // 2, s, s)

    def update(self):
        self.tick += 1
        if not self.collected:
            # Gentle sine bob while waiting to be collected
            self.y = self.base_y + math.sin(self.tick * 0.07) * self.BOUNCE
        else:
            # Float upward and fade after collection
            self.y    -= 1.5
            self.fade -= 12

    @property
    def alive(self):
        """False once the fade-out animation completes; used to cull the list."""
        return self.fade > 0

    def draw(self, surf):
        if self.collected:
            # Fading circle burst — simple collect feedback
            s = pygame.Surface((self.SIZE * 2, self.SIZE * 2), pygame.SRCALPHA)
            alpha = max(0, self.fade)
            c = (*self.colors[0], alpha)
            pygame.draw.circle(s, c, (self.SIZE, self.SIZE), self.SIZE // 2)
            surf.blit(s, (int(self.x) - self.SIZE, int(self.y) - self.SIZE))
            return

        # ── Spinning diamond ─────────────────────────────────────────────────
        angle = self.tick * 2.5   # degrees; drives the rotation each frame
        r     = self.SIZE // 2
        cx, cy = int(self.x), int(self.y)

        # Soft glow halo using a pulsing alpha circle on an SRCALPHA surface
        glow  = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        pulse = int(60 + 40 * math.sin(self.tick * 0.1))
        pygame.draw.circle(glow, (*self.colors[0], pulse), (r * 2, r * 2), r * 2)
        surf.blit(glow, (cx - r * 2, cy - r * 2))

        # Four diamond points rotated around the centre
        pts = []
        for i, ang in enumerate([angle, angle + 90, angle + 180, angle + 270]):
            rad  = math.radians(ang)
            dist = r if i % 2 == 0 else r * 0.6   # alternate long/short axes
            pts.append((cx + math.cos(rad) * dist, cy + math.sin(rad) * dist))

        pygame.draw.polygon(surf, self.colors[2], pts)                        # fill
        pygame.draw.polygon(surf, self.colors[1],                             # facet
                            [pts[0],
                             ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2 + 1),
                             pts[2]])
        pygame.draw.polygon(surf, self.colors[0], pts, 1)                     # outline

        # Cross sparkle that appears periodically
        if self.tick % 20 < 5:
            sp = int(math.sin(self.tick * 0.3) * r)
            pygame.draw.line(surf, (255, 255, 255), (cx - sp, cy), (cx + sp, cy), 1)
            pygame.draw.line(surf, (255, 255, 255), (cx, cy - sp), (cx, cy + sp), 1)


# ══════════════════════════════════════════════════════════════════════════════
# DOOR  (exit goal for each character)
# ══════════════════════════════════════════════════════════════════════════════

class Door:
    """
    An exit door that a character must stand in front of to win.

    kind:
      "fire"  – only Fireboy can activate
      "water" – only Watergirl can activate

    Both doors must be activated simultaneously (both characters standing at
    their respective doors) for the level to be completed, matching the
    co-operative mechanic of the original Fireboy & Watergirl.
    """

    W, H = 30, 46

    FIRE_COLORS  = {"frame": (180, 60, 10), "fill": (255, 120, 30),
                    "glow": (255, 160, 40), "icon": (255, 220, 80)}
    WATER_COLORS = {"frame": (15, 60, 160), "fill": (50, 140, 255),
                    "glow": (80, 200, 255), "icon": (180, 230, 255)}

    def __init__(self, x, y, kind="fire"):
        self.x    = x
        self.y    = y
        self.kind = kind
        self.tick = 0
        self.active = False
        self.colors = self.FIRE_COLORS if kind == "fire" else self.WATER_COLORS

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.W, self.H)

    def update(self, character):
        self.tick += 1
        char_rect = character.rect
        door_zone = self.rect.inflate(10, 6)
        self.active = char_rect.colliderect(door_zone)

    def draw(self, surf):
        r = self.rect
        cols = self.colors
        pulse = (math.sin(self.tick * 0.1) + 1) / 2

        if self.active:
            glow_surf = pygame.Surface((r.w + 40, r.h + 40), pygame.SRCALPHA)
            glow_alpha = int(80 + 60 * pulse)
            pygame.draw.ellipse(glow_surf,
                                (*cols["glow"], glow_alpha),
                                (0, 0, r.w + 40, r.h + 40))
            surf.blit(glow_surf, (r.x - 20, r.y - 20))

        draw_rounded_rect(surf, cols["frame"], r.inflate(4, 4), 4)
        draw_rounded_rect(surf, cols["fill"], r, 4)

        inner = pygame.Rect(r.x + 4, r.y + 4, r.w - 8, r.h - 8)
        highlight = lerp_color(cols["fill"], cols["glow"], 0.3 + 0.2 * pulse)
        draw_rounded_rect(surf, highlight, inner, 3)

        arch_rect = pygame.Rect(r.x + 6, r.y + 2, r.w - 12, 16)
        pygame.draw.arc(surf, cols["icon"], arch_rect, 0.2, math.pi - 0.2, 3)

        if self.kind == "fire":
            fx = r.centerx
            fy = r.y + r.h // 2 + 2
            fh = int(8 + 4 * pulse)
            pts = [(fx - 5, fy + 4), (fx, fy - fh), (fx + 5, fy + 4)]
            pygame.draw.polygon(surf, cols["icon"], pts)
            pts_inner = [(fx - 3, fy + 2), (fx, fy - fh + 4), (fx + 3, fy + 2)]
            pygame.draw.polygon(surf, (255, 255, 200), pts_inner)
        else:
            dx = r.centerx
            dy = r.y + r.h // 2 - 2
            drop_h = int(8 + 3 * pulse)
            pts = [(dx, dy - drop_h), (dx - 5, dy + 2), (dx + 5, dy + 2)]
            pygame.draw.polygon(surf, cols["icon"], pts)
            pygame.draw.circle(surf, cols["icon"], (dx, dy + 3), 5)
            pygame.draw.circle(surf, (200, 240, 255), (dx, dy + 2), 3)

        if self.active:
            check_y = r.y + r.h - 14
            check_x = r.centerx
            pygame.draw.lines(surf, (255, 255, 255), False,
                              [(check_x - 5, check_y),
                               (check_x - 1, check_y + 5),
                               (check_x + 6, check_y - 4)], 3)


# ══════════════════════════════════════════════════════════════════════════════
# BASE CHARACTER
# ══════════════════════════════════════════════════════════════════════════════

class Character:
    """
    Shared physics, collision, and jewel-collection logic for both players.

    Physics model
    -------------
    We use simple Euler integration:
        vy += GRAVITY   each frame
        x  += vx
        y  += vy

    Collision is resolved by separating the two axes.  Moving horizontally
    first, resolving, then moving vertically and resolving prevents the
    "corner sticking" artefact that occurs when both axes are resolved
    simultaneously.

    Hazard detection
    ----------------------------
    Previously, _on_hazard() was called only when a character LANDED ON TOP
    of a platform (vy > 0 branch of _resolve_y).  This meant that walking
    horizontally into a hazard pool at ground level never triggered death,
    because the character entered via the _resolve_x path, not _resolve_y.

    The fix is check_hazards(): called every frame from update(), it iterates
    all platforms and calls _on_hazard() for any hazard platform whose rect
    overlaps the character rect RIGHT NOW — regardless of which direction the
    character arrived from.  _on_hazard() inside _resolve_y is kept for the
    case of falling into a hazard from above, but check_hazards() is now the
    authoritative death check.
    """

    W, H = 28, 38   # character hitbox dimensions in pixels

    def __init__(self, x, y):
        self.x   = float(x)
        self.y   = float(y)
        self.vx  = 0.0
        self.vy  = 0.0
        self.on_ground  = False
        self.facing     = 1       # 1 = right, -1 = left; drives eye & arm direction
        self.tick       = 0
        self.walk_frame = 0       # fractional counter driving leg/arm animation
        self.score      = 0
        self.alive      = True

    @property
    def rect(self):
        """Always computed from (x, y) so collision is always current."""
        return pygame.Rect(int(self.x), int(self.y), self.W, self.H)

    # ── Physics ──────────────────────────────────────────────────────────────

    def apply_gravity(self):
        """Accumulate gravity; cap fall speed to prevent tunnelling."""
        self.vy += GRAVITY
        if self.vy > 18:
            self.vy = 18

    def move(self, platforms):
        """
        Translate the character by (vx, vy) and resolve collisions.
        Horizontal and vertical axes are handled in separate passes.
        """
        # Pass 1 — horizontal movement and resolution
        self.x += self.vx
        self._resolve_x(platforms)

        # Pass 2 — vertical movement and resolution
        self.y += self.vy
        self.on_ground = False
        self._resolve_y(platforms)

    def _resolve_x(self, platforms):
        """
        Push the character out of any platform it overlaps after horizontal movement.
        Only solid (non-hazard) platforms block horizontal movement; hazard pools
        are handled by check_hazards() so the character can walk into them before
        dying, which feels more natural than being blocked at the edge.
        """
        r = self.rect
        for p in platforms:
            if p.kind == "normal" and r.colliderect(p.rect):
                if self.vx > 0:           # moving right → push left edge clear
                    self.x = p.rect.left - self.W
                elif self.vx < 0:         # moving left  → push right edge clear
                    self.x = p.rect.right
                self.vx = 0

    def _resolve_y(self, platforms):
        """
        Push the character out of any platform it overlaps after vertical movement,
        and set on_ground when landing on top of a surface.
        """
        r = self.rect
        for p in platforms:
            if r.colliderect(p.rect):
                if self.vy > 0:           # falling → land on top of platform
                    self.y = p.rect.top - self.H
                    self.vy        = 0
                    self.on_ground = True
                    # Secondary hazard call for falling into a pool from above
                    self._on_hazard(p)
                elif self.vy < 0:         # jumping → hit head on underside
                    self.y = p.rect.bottom
                    self.vy = 0

    def _on_hazard(self, platform):
        """
        Called when the character collides with a hazard platform.
        Subclasses override this to implement element-specific death rules.
        """
        pass

    # ── Hazard check (frame-level overlap) ───────────────────────────────────

    def check_hazards(self, platforms):
        """
        Test direct overlap with every hazard platform every frame.

        This is the primary death-detection mechanism.  It catches cases that
        _on_hazard() misses — specifically, walking horizontally into a hazard
        pool at the same y-level (the character enters via _resolve_x, which
        for hazard platforms doesn't push back, so the body overlaps the pool
        rect on the very next frame).

        Design note: we shrink the character rect by 4 px horizontally before
        testing so that merely grazing the very edge of a pool while jumping
        over it doesn't instantly kill the player — a small grace margin that
        matches the visual width of the character sprite.
        """
        # A slightly inset rect prevents unfair "edge of pool" deaths
        inset_rect = self.rect.inflate(-4, -2)
        for p in platforms:
            if p.kind in ("lava", "water") and inset_rect.colliderect(p.rect):
                self._on_hazard(p)

    # ── Jewel collection ─────────────────────────────────────────────────────

    def collect_jewels(self, jewels):
        """Collect any jewel this character overlaps and is allowed to take."""
        for j in jewels:
            if not j.collected and self.rect.colliderect(j.rect):
                if self._can_collect(j):
                    j.collected = True
                    self.score += 2 if j.kind == "green" else 1

    def _can_collect(self, jewel):
        """
        Override in subclasses to restrict jewel collection by element type.
        Default allows collection of everything (useful for testing).
        """
        return True

    # ── Per-frame update ─────────────────────────────────────────────────────

    def update(self, platforms, jewels):
        """
        Master update called once per frame:
          1. Advance animation counters.
          2. Apply gravity and move.
          3. Check hazard overlap (the bug-fix addition).
          4. Collect jewels.
          5. Clamp to screen bounds.
        """
        self.tick += 1

        # Walk cycle: walk_frame advances proportionally to horizontal speed
        if abs(self.vx) > 0.1:
            self.walk_frame = (self.walk_frame + abs(self.vx) * 0.25) % 4
        else:
            self.walk_frame = 0

        self.apply_gravity()
        self.move(platforms)

        # ── BUG FIX: check hazard overlap every frame ──────────────────────
        # Previously missing; without this, walking into a pool at ground
        # level never set alive = False because _on_hazard was only reached
        # through _resolve_y (landing on top), not _resolve_x (side entry).
        self.check_hazards(platforms)

        self.collect_jewels(jewels)

        # Prevent characters from leaving the screen horizontally
        if self.x < 0:
            self.x = 0
        if self.x + self.W > WIDTH:
            self.x = WIDTH - self.W

    def draw(self, surf):
        """Implemented by each subclass — no shared body shape."""
        pass


# ══════════════════════════════════════════════════════════════════════════════
# FIREBOY
# ══════════════════════════════════════════════════════════════════════════════

class Fireboy(Character):
    """
    The fire-element player character.

    Element rules:
      - Dies on contact with water platforms.
      - Can collect fire jewels and green (neutral) jewels.
      - Is immune to lava — he can walk over lava platforms safely.

    Visual design: a flame-shaped body (teardrop pointing up) that IS
    the character, with two big yellow eyes, a smile, and tiny stub
    arms/legs — matching the original Fireboy & Watergirl art style.
    """

    BODY_FILL    = (240, 80, 15)
    BODY_LIGHT   = (255, 140, 40)
    OUTLINE      = (40, 10, 0)
    EYE_FILL     = (255, 230, 30)
    EYE_OUTLINE  = (80, 60, 0)
    LIMB_COLOR   = (210, 50, 10)

    def _on_hazard(self, platform):
        """Fireboy dies when touching a water platform."""
        if platform.kind == "water":
            self.alive = False

    def _can_collect(self, jewel):
        """Fireboy collects fire-coloured and neutral green jewels."""
        return jewel.kind in ("fire", "green")

    def draw(self, surf):
        cx = int(self.x) + self.W // 2
        top = int(self.y)
        body_cx = cx
        body_cy = top + 18
        body_rx = 14
        body_ry = 13

        # ── Flame-shaped body ────────────────────────────────────────────────
        # Built from an ellipse (lower face area) + flame tips on top
        flame_tips = []
        tip_data = [(-8, -18), (-3, -25), (2, -22), (7, -27), (11, -17)]
        for i, (ox, base_h) in enumerate(tip_data):
            flicker = math.sin(self.tick * 0.18 + i * 1.3) * 3
            flame_tips.append((body_cx + ox, body_cy + base_h + int(flicker)))

        body_outline = []
        steps = 16
        for i in range(steps + 1):
            angle = math.pi + (math.pi * i / steps)
            bx = body_cx + int(math.cos(angle) * (body_rx + 2))
            by = body_cy + int(math.sin(angle) * (body_ry + 1))
            body_outline.append((bx, by))

        full_shape = [body_outline[0]] + flame_tips + [body_outline[-1]] + list(reversed(body_outline))

        pygame.draw.polygon(surf, self.OUTLINE, full_shape)

        inner_tips = []
        for i, (ox, base_h) in enumerate(tip_data):
            flicker = math.sin(self.tick * 0.18 + i * 1.3) * 3
            inner_tips.append((body_cx + ox, body_cy + base_h + 3 + int(flicker)))

        inner_outline = []
        for i in range(steps + 1):
            angle = math.pi + (math.pi * i / steps)
            bx = body_cx + int(math.cos(angle) * body_rx)
            by = body_cy + int(math.sin(angle) * body_ry)
            inner_outline.append((bx, by))

        inner_shape = [inner_outline[0]] + inner_tips + [inner_outline[-1]] + list(reversed(inner_outline))
        pygame.draw.polygon(surf, self.BODY_FILL, inner_shape)

        highlight_rect = pygame.Rect(body_cx - body_rx + 4, body_cy - 6, body_rx, body_ry)
        hl_surf = pygame.Surface((highlight_rect.w, highlight_rect.h), pygame.SRCALPHA)
        pygame.draw.ellipse(hl_surf, (*self.BODY_LIGHT, 90),
                            (0, 0, highlight_rect.w, highlight_rect.h))
        surf.blit(hl_surf, highlight_rect.topleft)

        # ── Eyes (two big yellow circles) ────────────────────────────────────
        for side in (-1, 1):
            ex = body_cx + side * 6
            ey = body_cy + 1
            pygame.draw.circle(surf, self.OUTLINE, (ex, ey), 6)
            pygame.draw.circle(surf, self.EYE_FILL, (ex, ey), 5)
            pygame.draw.circle(surf, (0, 0, 0),
                               (ex + self.facing * 2, ey), 2)

        # ── Mouth (simple smile) ─────────────────────────────────────────────
        pygame.draw.arc(surf, self.OUTLINE,
                        pygame.Rect(body_cx - 5, body_cy + 5, 10, 6),
                        math.pi + 0.4, 2 * math.pi - 0.4, 2)

        # ── Tiny stub arms ───────────────────────────────────────────────────
        arm_swing = (int(math.sin(self.walk_frame * math.pi / 2) * 4)
                     if abs(self.vx) > 0.1 else 0)
        for side, sw in [(-1, 1), (1, -1)]:
            ax = body_cx + side * (body_rx + 1)
            ay = body_cy + 6
            pygame.draw.line(surf, self.LIMB_COLOR,
                             (ax, ay), (ax + side * 6, ay + 4 + sw * arm_swing), 4)
            pygame.draw.circle(surf, self.LIMB_COLOR,
                               (ax + side * 6, ay + 4 + sw * arm_swing), 3)

        # ── Tiny stub legs ───────────────────────────────────────────────────
        for side in (-1, 1):
            foot_swing = (int(math.sin((self.walk_frame + side * 2) * math.pi / 2) * 5)
                          if abs(self.vx) > 0.1 else 0)
            lx = body_cx + side * 5
            ly = body_cy + body_ry
            pygame.draw.line(surf, self.LIMB_COLOR,
                             (lx, ly), (lx + foot_swing // 2, ly + 10 + foot_swing), 4)
            pygame.draw.circle(surf, self.LIMB_COLOR,
                               (lx + foot_swing // 2, ly + 10 + foot_swing), 3)


# ══════════════════════════════════════════════════════════════════════════════
# WATERGIRL
# ══════════════════════════════════════════════════════════════════════════════

class Watergirl(Character):
    """
    The water-element player character.

    Element rules:
      - Dies on contact with lava platforms.
      - Can collect water jewels and green (neutral) jewels.
      - Is immune to water — she can walk through water platforms safely.

    Visual design: a large round blue bubble that IS the character, with
    a water-bun on top, two big eyes with half-lid highlights, a smile,
    animated swirl patterns, and tiny stub arms/legs — matching the
    original Fireboy & Watergirl art style.
    """

    BODY_FILL    = (80, 180, 255)
    BODY_DARK    = (40, 130, 220)
    OUTLINE      = (10, 40, 100)
    SWIRL_COLOR  = (50, 150, 240)
    BUN_COLOR    = (100, 200, 255)
    BUN_DARK     = (60, 160, 230)
    LIMB_COLOR   = (60, 160, 255)

    def _on_hazard(self, platform):
        """Watergirl dies when touching a lava platform."""
        if platform.kind == "lava":
            self.alive = False

    def _can_collect(self, jewel):
        """Watergirl collects water-coloured and neutral green jewels."""
        return jewel.kind in ("water", "green")

    def draw(self, surf):
        cx = int(self.x) + self.W // 2
        top = int(self.y)
        body_cx = cx
        body_cy = top + 16
        body_r = 15

        # ── Water bun / ponytail on top ──────────────────────────────────────
        bun_cx = body_cx + 2
        bun_cy = body_cy - body_r - 4
        wobble = math.sin(self.tick * 0.1) * 2
        pygame.draw.circle(surf, self.OUTLINE, (bun_cx, bun_cy + int(wobble)), 10)
        pygame.draw.circle(surf, self.BUN_COLOR, (bun_cx, bun_cy + int(wobble)), 8)
        pygame.draw.circle(surf, self.BUN_DARK,
                           (bun_cx - 2, bun_cy - 2 + int(wobble)), 4)
        pygame.draw.circle(surf, (140, 220, 255),
                           (bun_cx + 3, bun_cy + 2 + int(wobble)), 3)
        pygame.draw.line(surf, self.OUTLINE,
                         (bun_cx, bun_cy + 8 + int(wobble)),
                         (body_cx, body_cy - body_r + 2), 3)

        # ── Round body (big blue circle) ─────────────────────────────────────
        pygame.draw.circle(surf, self.OUTLINE, (body_cx, body_cy), body_r + 2)
        pygame.draw.circle(surf, self.BODY_FILL, (body_cx, body_cy), body_r)

        # Animated swirl/wave patterns inside the body
        swirl_angle = self.tick * 0.04
        for i in range(3):
            sa = swirl_angle + i * 2.1
            sx = body_cx + int(math.cos(sa) * 6)
            sy = body_cy + int(math.sin(sa) * 5) - 2
            sw_surf = pygame.Surface((12, 8), pygame.SRCALPHA)
            pygame.draw.arc(sw_surf, (*self.SWIRL_COLOR, 120),
                            (0, 0, 12, 8), 0.3, math.pi - 0.3, 2)
            surf.blit(sw_surf, (sx - 6, sy - 4))

        hl_surf = pygame.Surface((14, 14), pygame.SRCALPHA)
        pygame.draw.circle(hl_surf, (180, 230, 255, 80), (7, 7), 7)
        surf.blit(hl_surf, (body_cx - body_r + 3, body_cy - body_r + 4))

        # ── Eyes (two big eyes with half-lid look) ───────────────────────────
        for side in (-1, 1):
            ex = body_cx + side * 6
            ey = body_cy - 1
            pygame.draw.circle(surf, (255, 255, 255), (ex, ey), 5)
            pygame.draw.circle(surf, self.OUTLINE, (ex, ey), 5, 1)
            pupil_x = ex + self.facing * 2
            pygame.draw.circle(surf, (0, 0, 0), (pupil_x, ey + 1), 2)
            lid_pts = [
                (ex - 5, ey - 2),
                (ex, ey - 5),
                (ex + 5, ey - 2),
            ]
            pygame.draw.polygon(surf, self.BODY_FILL, lid_pts)
            pygame.draw.lines(surf, self.OUTLINE, False, lid_pts, 1)

        # ── Mouth (simple smile) ─────────────────────────────────────────────
        pygame.draw.arc(surf, self.OUTLINE,
                        pygame.Rect(body_cx - 5, body_cy + 5, 10, 6),
                        math.pi + 0.4, 2 * math.pi - 0.4, 2)

        # ── Tiny stub arms ───────────────────────────────────────────────────
        arm_swing = (int(math.sin(self.walk_frame * math.pi / 2) * 4)
                     if abs(self.vx) > 0.1 else 0)
        for side, sw in [(-1, 1), (1, -1)]:
            ax = body_cx + side * (body_r + 1)
            ay = body_cy + 6
            pygame.draw.line(surf, self.LIMB_COLOR,
                             (ax, ay), (ax + side * 6, ay + 4 + sw * arm_swing), 4)
            pygame.draw.circle(surf, self.LIMB_COLOR,
                               (ax + side * 6, ay + 4 + sw * arm_swing), 3)

        # ── Tiny stub legs ───────────────────────────────────────────────────
        for side in (-1, 1):
            foot_swing = (int(math.sin((self.walk_frame + side * 2) * math.pi / 2) * 5)
                          if abs(self.vx) > 0.1 else 0)
            lx = body_cx + side * 5
            ly = body_cy + body_r
            pygame.draw.line(surf, self.LIMB_COLOR,
                             (lx, ly), (lx + foot_swing // 2, ly + 10 + foot_swing), 4)
            pygame.draw.circle(surf, self.LIMB_COLOR,
                               (lx + foot_swing // 2, ly + 10 + foot_swing), 3)


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL
# ══════════════════════════════════════════════════════════════════════════════

def build_level():
    """
    Construct and return the list of platforms and jewels for the level.

    Design notes
    ------------
    Platforms are listed in logical groups (ground, wall ledges, mid-air
    platforms, hazard pools) rather than sorted by position, making it easier
    to reason about the layout when editing.

    Jewel placement follows the original game's convention:
      - Fire jewels cluster on Fireboy's side (left / centre-left).
      - Water jewels cluster on Watergirl's side (right / centre-right).
      - Green jewels sit in the middle as shared objectives that draw both
        players to the same area and encourage cooperation.

    The h=20 on the ground-level hazard pools makes them flush with the
    ground (ground y=560, pool y=560, ground h=40 >= pool h=20) so characters
    walking along the floor overlap the pool rect — exactly the case that the
    old code failed to detect and the new check_hazards() fixes.
    """
    platforms = [
        # ── Ground ────────────────────────────────────────────────────────
        Platform(0,   560, 900, 40),           # main floor

        # ── Left-side wall ledges ────────────────────────────────────────
        Platform(0,   420, 140),
        Platform(0,   280, 100),

        # ── Right-side wall ledges ───────────────────────────────────────
        Platform(760, 420, 140),
        Platform(800, 280, 100),

        # ── Mid-air platforms ────────────────────────────────────────────
        Platform(180, 460, 120),
        Platform(350, 390, 140),
        Platform(530, 320, 120),
        Platform(260, 300, 100),
        Platform(150, 200, 120),
        Platform(600, 220, 130),
        Platform(420, 160, 100),

        # ── Ground-level hazard pools ────────────────────────────────────
        # h=20 so the pool rect sits inside the ground rect; characters
        # walking along the floor will overlap these rects every frame,
        # which check_hazards() now catches correctly.
        Platform(200, 560, 140, 20, "lava"),   # lava pool — kills Watergirl
        Platform(560, 560, 140, 20, "water"),  # water pool — kills Fireboy
    ]

    jewels = [
        # Fire jewels (Fireboy only)
        Jewel(230, 440, "fire"),
        Jewel(280, 280, "fire"),
        Jewel(165, 180, "fire"),

        # Water jewels (Watergirl only)
        Jewel(615, 300, "water"),
        Jewel(830, 260, "water"),
        Jewel(640, 200, "water"),

        # Green jewels (either player)
        Jewel(400, 365, "green"),
        Jewel(450, 140, "green"),
        Jewel(550, 190, "green"),
    ]

    doors = [
        Door(180, 200 - Door.H, "fire"),
        Door(650, 220 - Door.H, "water"),
    ]

    return platforms, jewels, doors


# ══════════════════════════════════════════════════════════════════════════════
# HUD AND OVERLAY SCREENS
# ══════════════════════════════════════════════════════════════════════════════

def draw_hud(surf, fireboy, watergirl, elapsed):
    """
    Render diamond scores, live timer, and control reminder.
    """
    total = fireboy.score + watergirl.score
    fb_surf = font_small.render(f"Fireboy: {fireboy.score}",    True, (255, 140, 40))
    wg_surf = font_small.render(f"Watergirl: {watergirl.score}", True, (80, 180, 255))
    tot_surf = font_small.render(f"Total: {total} pts", True, (180, 255, 140))
    surf.blit(fb_surf, (10, 10))
    surf.blit(wg_surf, (10, 34))
    surf.blit(tot_surf, (10, 58))

    timer_txt = font_big.render(format_time(elapsed), True, (255, 255, 255))
    surf.blit(timer_txt, (WIDTH // 2 - timer_txt.get_width() // 2, 8))

    green_hint = font_small.render("Green = 2x pts", True, (100, 220, 130))
    surf.blit(green_hint, (WIDTH // 2 - green_hint.get_width() // 2, 38))

    ctrl1 = font_small.render("Fireboy: LEFT RIGHT UP",   True, (180, 100, 60))
    ctrl2 = font_small.render("Watergirl: A D W",         True, (60,  130, 200))
    surf.blit(ctrl1, (WIDTH - 230, 10))
    surf.blit(ctrl2, (WIDTH - 230, 34))


def draw_death_screen(surf, who):
    """Semi-transparent dark overlay with a 'died' message."""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    surf.blit(overlay, (0, 0))
    msg = f"{who} died!  Press R to restart"
    txt = font_big.render(msg, True, (255, 80, 80))
    surf.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 20))


def draw_win_screen(surf, score, elapsed, records, new_high):
    """Overlay shown when both characters reach their doors."""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surf.blit(overlay, (0, 0))

    txt = font_title.render("Level Complete!", True, (255, 220, 80))
    surf.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 60))

    score_txt = font_big.render(f"Diamonds: {score} pts", True, (180, 255, 140))
    surf.blit(score_txt, (WIDTH // 2 - score_txt.get_width() // 2, 125))

    time_txt = font_big.render(f"Time: {format_time(elapsed)}", True, (255, 255, 255))
    surf.blit(time_txt, (WIDTH // 2 - time_txt.get_width() // 2, 160))

    if new_high:
        nb = font_menu.render("NEW HIGH SCORE!", True, (255, 220, 50))
        surf.blit(nb, (WIDTH // 2 - nb.get_width() // 2, 200))

    hdr = font_menu.render("Leaderboard", True, (255, 200, 100))
    surf.blit(hdr, (WIDTH // 2 - hdr.get_width() // 2, 235))

    col_hdr = font_small.render("  #     SCORE       TIME", True, (160, 155, 145))
    surf.blit(col_hdr, (WIDTH // 2 - 100, 262))

    for i, rec in enumerate(records[:7]):
        rank_color = ((255, 215, 0) if i == 0
                      else (200, 200, 210) if i == 1
                      else (180, 120, 60) if i == 2
                      else (180, 175, 165))
        row = font_small.render(
            f"#{i + 1:>2}      {rec['score']:>3} pts     {format_time(rec['time'])}",
            True, rank_color)
        surf.blit(row, (WIDTH // 2 - 100, 286 + i * 24))

    restart = font_small.render("Press R to play again", True, (180, 175, 165))
    surf.blit(restart, (WIDTH // 2 - restart.get_width() // 2, HEIGHT - 50))


# ══════════════════════════════════════════════════════════════════════════════
# MENU BUTTON
# ══════════════════════════════════════════════════════════════════════════════

class Button:
    """A clickable rectangle with text, hover highlight, and rounded corners."""

    def __init__(self, x, y, w, h, text, color, hover_color, text_color=(255, 255, 255)):
        self.rect        = pygame.Rect(x, y, w, h)
        self.text        = text
        self.color       = color
        self.hover_color = hover_color
        self.text_color  = text_color
        self.hovered     = False

    def update(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surf):
        col = self.hover_color if self.hovered else self.color
        draw_rounded_rect(surf, (0, 0, 0), self.rect.inflate(4, 4), 12)
        draw_rounded_rect(surf, col, self.rect, 10)
        if self.hovered:
            glow = pygame.Surface((self.rect.w + 16, self.rect.h + 16), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*col, 40), (0, 0, glow.get_width(), glow.get_height()),
                             border_radius=14)
            surf.blit(glow, (self.rect.x - 8, self.rect.y - 8))
        txt = font_menu.render(self.text, True, self.text_color)
        surf.blit(txt, (self.rect.centerx - txt.get_width() // 2,
                        self.rect.centery - txt.get_height() // 2))

    def clicked(self, event):
        return (event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.hovered)


# ══════════════════════════════════════════════════════════════════════════════
# START SCREEN & INSTRUCTIONS SCREEN
# ══════════════════════════════════════════════════════════════════════════════

def start_screen():
    """
    Title screen shown when the game launches.
    Returns when the player clicks Play; clicking Instructions opens that page.
    """
    bg = Background()

    btn_w, btn_h = 220, 50
    play_btn = Button(WIDTH // 2 - btn_w // 2, 330, btn_w, btn_h,
                      "Play", (200, 60, 20), (255, 100, 40))
    instr_btn = Button(WIDTH // 2 - btn_w // 2, 395, btn_w, btn_h,
                       "Instructions", (30, 90, 200), (60, 140, 255))
    times_btn = Button(WIDTH // 2 - btn_w // 2, 460, btn_w, btn_h,
                       "Best Times", (120, 90, 20), (180, 140, 40))

    tick = 0
    while True:
        clock.tick(FPS)
        tick += 1
        mouse = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if play_btn.clicked(event):
                return
            if instr_btn.clicked(event):
                instructions_screen()
            if times_btn.clicked(event):
                best_times_screen()

        play_btn.update(mouse)
        instr_btn.update(mouse)
        times_btn.update(mouse)
        bg.update()

        bg.draw(screen)

        # Title text with a gentle vertical bob
        bob = math.sin(tick * 0.04) * 4
        title1 = font_title.render("Fireboy", True, (255, 140, 40))
        title2 = font_title.render("&", True, (200, 200, 200))
        title3 = font_title.render("Watergirl", True, (80, 180, 255))
        total_w = title1.get_width() + title2.get_width() + title3.get_width() + 20
        tx = WIDTH // 2 - total_w // 2
        ty = 120 + int(bob)
        screen.blit(title1, (tx, ty))
        tx += title1.get_width() + 10
        screen.blit(title2, (tx, ty))
        tx += title2.get_width() + 10
        screen.blit(title3, (tx, ty))

        subtitle = font_small.render("A two-player co-operative platformer", True, (180, 170, 160))
        screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 190 + int(bob)))

        # Draw small preview characters on the title screen
        fire_preview_x = WIDTH // 2 - 60
        water_preview_x = WIDTH // 2 + 40
        preview_y = 240
        _draw_mini_fireboy(screen, fire_preview_x, preview_y + int(bob), tick)
        _draw_mini_watergirl(screen, water_preview_x, preview_y + int(bob), tick)

        play_btn.draw(screen)
        instr_btn.draw(screen)
        times_btn.draw(screen)

        hint = font_small.render("Press ESC to quit anytime", True, (120, 110, 100))
        screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 40))

        pygame.display.flip()


def _draw_mini_fireboy(surf, x, y, tick):
    """Small Fireboy preview for the title screen."""
    cx, cy = x + 14, y + 14
    for i in range(3):
        flicker = math.sin(tick * 0.2 + i * 1.3) * 2
        fx = cx + (i - 1) * 4
        pts = [(fx - 2, cy - 8), (fx, cy - 16 + int(flicker)), (fx + 2, cy - 8)]
        pygame.draw.polygon(surf, (255, 160 + i * 30, 20), pts)
    pygame.draw.circle(surf, (40, 10, 0), (cx, cy), 11)
    pygame.draw.circle(surf, (240, 80, 15), (cx, cy), 9)
    for side in (-1, 1):
        pygame.draw.circle(surf, (255, 230, 30), (cx + side * 4, cy - 1), 4)
        pygame.draw.circle(surf, (0, 0, 0), (cx + side * 4, cy - 1), 2)
    pygame.draw.arc(surf, (40, 10, 0), pygame.Rect(cx - 4, cy + 3, 8, 5),
                    math.pi + 0.4, 2 * math.pi - 0.4, 1)


def _draw_mini_watergirl(surf, x, y, tick):
    """Small Watergirl preview for the title screen."""
    cx, cy = x + 14, y + 14
    wobble = math.sin(tick * 0.1) * 1
    pygame.draw.circle(surf, (10, 40, 100), (cx + 1, cy - 12 + int(wobble)), 7)
    pygame.draw.circle(surf, (100, 200, 255), (cx + 1, cy - 12 + int(wobble)), 5)
    pygame.draw.circle(surf, (10, 40, 100), (cx, cy), 11)
    pygame.draw.circle(surf, (80, 180, 255), (cx, cy), 9)
    for side in (-1, 1):
        pygame.draw.circle(surf, (255, 255, 255), (cx + side * 4, cy - 1), 4)
        pygame.draw.circle(surf, (0, 0, 0), (cx + side * 4, cy), 2)
        lid = [(cx + side * 4 - 4, cy - 2), (cx + side * 4, cy - 5), (cx + side * 4 + 4, cy - 2)]
        pygame.draw.polygon(surf, (80, 180, 255), lid)
    pygame.draw.arc(surf, (10, 40, 100), pygame.Rect(cx - 4, cy + 3, 8, 5),
                    math.pi + 0.4, 2 * math.pi - 0.4, 1)


def instructions_screen():
    """
    Full-screen instructions page.  Returns when the player clicks Back.
    """
    bg = Background()
    back_btn = Button(WIDTH // 2 - 100, HEIGHT - 80, 200, 45,
                      "Back", (80, 60, 40), (140, 100, 60))

    instructions = [
        ("GOAL",    "Both characters must reach their exit doors at the same time!"),
        ("",        ""),
        ("FIREBOY", "Arrow Keys  —  LEFT / RIGHT to move,  UP to jump"),
        ("",        "Collects fire (orange) and green jewels"),
        ("",        "Safe on lava,  dies on water"),
        ("",        ""),
        ("WATERGIRL", "W A S D  —  A / D to move,  W to jump"),
        ("",          "Collects water (blue) and green jewels"),
        ("",          "Safe on water,  dies on lava"),
        ("",        ""),
        ("RESTART",  "Press  R  at any time to restart the level"),
    ]

    while True:
        clock.tick(FPS)
        mouse = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if back_btn.clicked(event):
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return

        back_btn.update(mouse)
        bg.update()
        bg.draw(screen)

        header = font_title.render("How to Play", True, (255, 220, 140))
        screen.blit(header, (WIDTH // 2 - header.get_width() // 2, 40))

        y = 120
        for label, desc in instructions:
            if label == "" and desc == "":
                y += 12
                continue
            if label:
                lbl = font_menu.render(label, True, (255, 180, 80) if label == "FIREBOY"
                                       else (80, 200, 255) if label == "WATERGIRL"
                                       else (255, 220, 140))
                screen.blit(lbl, (120, y))
                y += 30
            if desc:
                dtxt = font_small.render(desc, True, (200, 195, 185))
                screen.blit(dtxt, (140, y))
                y += 28

        back_btn.draw(screen)
        pygame.display.flip()


def best_times_screen():
    """Full-screen leaderboard showing saved run records (score + time)."""
    bg = Background()
    back_btn = Button(WIDTH // 2 - 100, HEIGHT - 80, 200, 45,
                      "Back", (80, 60, 40), (140, 100, 60))

    while True:
        clock.tick(FPS)
        mouse = pygame.mouse.get_pos()
        records = load_records()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if back_btn.clicked(event):
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return

        back_btn.update(mouse)
        bg.update()
        bg.draw(screen)

        header = font_title.render("Leaderboard", True, (255, 220, 140))
        screen.blit(header, (WIDTH // 2 - header.get_width() // 2, 50))

        sub = font_small.render("Ranked by diamonds (green = 2x),  ties broken by time",
                                True, (160, 155, 145))
        screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 108))

        if not records:
            empty = font_menu.render("No runs recorded yet — go play!", True, (180, 175, 165))
            screen.blit(empty, (WIDTH // 2 - empty.get_width() // 2, 200))
        else:
            col_hdr = font_small.render("  #       SCORE          TIME", True, (140, 135, 125))
            screen.blit(col_hdr, (WIDTH // 2 - 110, 140))

            for i, rec in enumerate(records):
                rank_color = ((255, 215, 0) if i == 0
                              else (200, 200, 210) if i == 1
                              else (180, 120, 60) if i == 2
                              else (180, 175, 165))
                row_txt = font_menu.render(
                    f"#{i + 1:>2}       {rec['score']:>3} pts       {format_time(rec['time'])}",
                    True, rank_color)
                surf_y = 170 + i * 36
                screen.blit(row_txt, (WIDTH // 2 - 110, surf_y))

        back_btn.draw(screen)
        pygame.display.flip()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN GAME LOOP
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Entry point — owns the top-level game state and runs the frame loop.

    State machine:
      game_over=False, winner=False → normal play
      game_over=True               → death screen; R restarts
      winner=True                  → win screen;   R restarts

    Win condition: both Fireboy and Watergirl must stand at their
    respective exit doors at the same time.

    Restarting calls main() recursively and immediately returns, which
    unwinds the old call stack.  For a production game you'd use a proper
    state machine, but for a small project this is simple and clear.
    """
    bg = Background()
    platforms, jewels, doors = build_level()
    fire_door  = doors[0]
    water_door = doors[1]

    # Spawn characters at opposite ends of the ground
    fireboy   = Fireboy  (80,  500)
    watergirl = Watergirl(780, 500)

    game_over   = False
    winner      = False
    dead_msg    = ""
    start_tick  = pygame.time.get_ticks()
    elapsed     = 0.0
    final_time  = 0.0
    final_score = 0
    new_high    = False
    records     = load_records()

    while True:
        clock.tick(FPS)

        # ── Event handling ────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    main()   # restart by re-entering main; old call returns below
                    return

        # ── Update (only when game is still active) ───────────────────────────
        if not game_over and not winner:
            elapsed = (pygame.time.get_ticks() - start_tick) / 1000.0
            keys = pygame.key.get_pressed()

            # Fireboy — arrow keys
            # vx is reset to 0 each frame so releasing a key stops immediately.
            # This is intentional: the original game has no momentum/friction.
            fireboy.vx = 0
            if keys[pygame.K_LEFT]:
                fireboy.vx     = -MOVE_SPEED
                fireboy.facing = -1
            if keys[pygame.K_RIGHT]:
                fireboy.vx     = MOVE_SPEED
                fireboy.facing = 1
            if keys[pygame.K_UP] and fireboy.on_ground:
                fireboy.vy = JUMP_SPEED   # negative = upward in pygame coords

            # Watergirl — WASD
            watergirl.vx = 0
            if keys[pygame.K_a]:
                watergirl.vx     = -MOVE_SPEED
                watergirl.facing = -1
            if keys[pygame.K_d]:
                watergirl.vx     = MOVE_SPEED
                watergirl.facing = 1
            if keys[pygame.K_w] and watergirl.on_ground:
                watergirl.vy = JUMP_SPEED

            # Advance background, platform animations, and jewel animations
            bg.update()
            for p in platforms:
                p.update()
            for j in jewels:
                j.update()

            # Remove jewels whose fade-out animation has fully completed
            jewels = [j for j in jewels if j.alive]

            # Update characters (physics + hazard check + jewel collection)
            fireboy.update  (platforms, jewels)
            watergirl.update(platforms, jewels)

            # Update doors (track whether correct character is standing at each)
            fire_door.update(fireboy)
            water_door.update(watergirl)

            # ── Win / lose checks ─────────────────────────────────────────────
            if not fireboy.alive:
                game_over = True
                dead_msg  = "Fireboy"
            if not watergirl.alive:
                game_over = True
                dead_msg  = "Watergirl"

            # Win when both characters are at their respective doors
            if fire_door.active and water_door.active:
                winner = True
                final_time = elapsed
                final_score = fireboy.score + watergirl.score
                new_high = is_new_high(final_score, final_time, records)
                records.append({"score": final_score, "time": final_time})
                records = sorted(records, key=_rank_key)[:MAX_RECORDS]
                save_records(records)

        # ── Draw ─────────────────────────────────────────────────────────────
        bg.draw(screen)
        for p in platforms:
            p.draw(screen)
        fire_door.draw(screen)
        water_door.draw(screen)
        for j in jewels:
            j.draw(screen)
        fireboy.draw  (screen)
        watergirl.draw(screen)
        draw_hud(screen, fireboy, watergirl, elapsed if not winner else final_time)

        if game_over:
            draw_death_screen(screen, dead_msg)
        if winner:
            draw_win_screen(screen, final_score, final_time, records, new_high)

        pygame.display.flip()


if __name__ == "__main__":
    start_screen()
    main()