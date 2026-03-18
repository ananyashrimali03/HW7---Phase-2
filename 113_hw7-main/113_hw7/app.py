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
                    self.score += 1

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

    Visual design: flame-shaped hair animated with sine waves,
    warm orange body, golden eyes with an orange iris glow.
    """

    BODY_COLOR   = (210, 50, 10)
    DARK_COLOR   = (140, 20, 0)
    FLAME_COLORS = [(255, 220, 50), (255, 130, 20), (210, 50, 10)]

    def _on_hazard(self, platform):
        """Fireboy dies when touching a water platform."""
        if platform.kind == "water":
            self.alive = False

    def _can_collect(self, jewel):
        """Fireboy collects fire-coloured and neutral green jewels."""
        return jewel.kind in ("fire", "green")

    def draw(self, surf):
        cx = int(self.x) + self.W // 2
        cy = int(self.y) + self.H // 2

        # ── Flame hair ───────────────────────────────────────────────────────
        # Three flame tongues offset by 1.2 radians; height and offset driven
        # by a sine wave so they dance independently.
        for i in range(3):
            offset = math.sin(self.tick * 0.18 + i * 1.2) * 4
            fh = 10 + i * 3
            fc = self.FLAME_COLORS[i]
            pts = [
                (cx + (i - 1) * 7,              cy - self.H // 2 + 4),
                (cx + (i - 1) * 7 - 4 * self.facing, cy - self.H // 2 - fh + offset),
                (cx + (i - 1) * 7 + 4 * self.facing, cy - self.H // 2 - fh + offset + 3),
            ]
            pygame.draw.polygon(surf, fc, pts)

        # ── Body ─────────────────────────────────────────────────────────────
        body_rect = pygame.Rect(int(self.x) + 2, int(self.y) + 8, self.W - 4, self.H - 14)
        draw_rounded_rect(surf, self.DARK_COLOR, body_rect.inflate(4, 2), 10)  # shadow
        draw_rounded_rect(surf, self.BODY_COLOR, body_rect, 10)

        # ── Legs ─────────────────────────────────────────────────────────────
        # foot_offset alternates between the two legs using a phase offset of 2
        leg_y = int(self.y) + self.H - 10
        for side in (-1, 1):
            foot_offset = (
                int(math.sin((self.walk_frame + side * 2) * math.pi / 2) * 5)
                if abs(self.vx) > 0.1 else 0
            )
            pygame.draw.line(surf, self.DARK_COLOR,
                             (cx + side * 5, leg_y),
                             (cx + side * 7, leg_y + 8 + foot_offset), 5)

        # ── Arms ─────────────────────────────────────────────────────────────
        # Counter-swing: left arm forward when right leg is forward
        arm_swing = int(math.sin(self.walk_frame * math.pi / 2) * 6) if abs(self.vx) > 0.1 else 0
        pygame.draw.line(surf, self.DARK_COLOR,
                         (cx - 8, int(self.y) + 14),
                         (cx - 14, int(self.y) + 22 + arm_swing), 4)
        pygame.draw.line(surf, self.DARK_COLOR,
                         (cx + 8, int(self.y) + 14),
                         (cx + 14, int(self.y) + 22 - arm_swing), 4)

        # ── Eye ──────────────────────────────────────────────────────────────
        # Eye position shifts left/right with self.facing so it always looks
        # in the direction of movement.
        eye_x = cx + self.facing * 5
        pygame.draw.circle(surf, (255, 255, 255), (eye_x, int(self.y) + 16), 5)
        pygame.draw.circle(surf, (255, 200, 50),  (eye_x, int(self.y) + 16), 3)
        pygame.draw.circle(surf, (0, 0, 0),        (eye_x + self.facing, int(self.y) + 16), 2)

        # ── Ambient glow aura ─────────────────────────────────────────────────
        aura  = pygame.Surface((60, 70), pygame.SRCALPHA)
        pulse = int(30 + 15 * math.sin(self.tick * 0.12))
        pygame.draw.ellipse(aura, (255, 80, 20, pulse), (5, 5, 50, 60))
        surf.blit(aura, (cx - 30, cy - 35))


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

    Visual design: droplet-shaped hair with a ripple arc across the torso,
    cool blue palette, soft cyan iris.
    """

    BODY_COLOR   = (30, 100, 220)
    DARK_COLOR   = (15, 60, 160)
    DROPLET_COLS = [(180, 230, 255), (80, 180, 255), (30, 100, 220)]

    def _on_hazard(self, platform):
        """Watergirl dies when touching a lava platform."""
        if platform.kind == "lava":
            self.alive = False

    def _can_collect(self, jewel):
        """Watergirl collects water-coloured and neutral green jewels."""
        return jewel.kind in ("water", "green")

    def draw(self, surf):
        cx = int(self.x) + self.W // 2
        cy = int(self.y) + self.H // 2

        # ── Droplet hair ──────────────────────────────────────────────────────
        for i in range(3):
            offset = math.sin(self.tick * 0.14 + i * 1.0) * 3
            dh = 9 + i * 2
            dc = self.DROPLET_COLS[i]
            dx = cx + (i - 1) * 7
            dy = int(self.y) - 2 + int(offset)
            # Teardrop = triangle tip + circle base
            pts = [(dx, dy), (dx - 4, dy - dh), (dx + 4, dy - dh)]
            pygame.draw.polygon(surf, dc, pts)
            pygame.draw.circle(surf, dc, (dx, dy), 4)

        # ── Body ──────────────────────────────────────────────────────────────
        body_rect = pygame.Rect(int(self.x) + 2, int(self.y) + 8, self.W - 4, self.H - 14)
        draw_rounded_rect(surf, self.DARK_COLOR, body_rect.inflate(4, 2), 10)
        draw_rounded_rect(surf, self.BODY_COLOR, body_rect, 10)

        # Ripple arc — animated vertically with a sine, suggesting flowing water
        ripple_y = int(self.y) + 18 + int(math.sin(self.tick * 0.1) * 2)
        pygame.draw.arc(surf, (100, 180, 255),
                        pygame.Rect(int(self.x) + 6, ripple_y, self.W - 12, 8),
                        0, math.pi, 2)

        # ── Legs ──────────────────────────────────────────────────────────────
        leg_y = int(self.y) + self.H - 10
        for side in (-1, 1):
            foot_offset = (
                int(math.sin((self.walk_frame + side * 2) * math.pi / 2) * 5)
                if abs(self.vx) > 0.1 else 0
            )
            pygame.draw.line(surf, self.DARK_COLOR,
                             (cx + side * 5, leg_y),
                             (cx + side * 7, leg_y + 8 + foot_offset), 5)

        # ── Arms ──────────────────────────────────────────────────────────────
        arm_swing = int(math.sin(self.walk_frame * math.pi / 2) * 6) if abs(self.vx) > 0.1 else 0
        pygame.draw.line(surf, self.DARK_COLOR,
                         (cx - 8, int(self.y) + 14),
                         (cx - 14, int(self.y) + 22 + arm_swing), 4)
        pygame.draw.line(surf, self.DARK_COLOR,
                         (cx + 8, int(self.y) + 14),
                         (cx + 14, int(self.y) + 22 - arm_swing), 4)

        # ── Eye ───────────────────────────────────────────────────────────────
        eye_x = cx + self.facing * 5
        pygame.draw.circle(surf, (220, 240, 255), (eye_x, int(self.y) + 16), 5)
        pygame.draw.circle(surf, (100, 200, 255), (eye_x, int(self.y) + 16), 3)
        pygame.draw.circle(surf, (0, 0, 0),        (eye_x + self.facing, int(self.y) + 16), 2)

        # ── Ambient glow aura ─────────────────────────────────────────────────
        aura  = pygame.Surface((60, 70), pygame.SRCALPHA)
        pulse = int(30 + 15 * math.sin(self.tick * 0.10 + 1.5))
        pygame.draw.ellipse(aura, (50, 150, 255, pulse), (5, 5, 50, 60))
        surf.blit(aura, (cx - 30, cy - 35))


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

        # ── Elevated hazard ledges ───────────────────────────────────────
        Platform(310, 460, 80, 14, "lava"),
        Platform(510, 390, 80, 14, "water"),
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

def draw_hud(surf, fireboy, watergirl):
    """
    Render the score counters and control reminder in the corners.
    Kept as a free function rather than a class because it owns no state —
    it just reads from the character objects each frame.
    """
    fb_surf = font_small.render(f"Fireboy: {fireboy.score}",    True, (255, 140, 40))
    wg_surf = font_small.render(f"Watergirl: {watergirl.score}", True, (80, 180, 255))
    surf.blit(fb_surf, (10, 10))
    surf.blit(wg_surf, (10, 34))

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


def draw_win_screen(surf):
    """Overlay shown when both characters reach their doors."""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    surf.blit(overlay, (0, 0))
    txt = font_big.render(
        "Level Complete!  Press R to restart", True, (255, 220, 80)
    )
    surf.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 20))


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

    game_over = False
    winner    = False
    dead_msg  = ""

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
        draw_hud(screen, fireboy, watergirl)

        if game_over:
            draw_death_screen(screen, dead_msg)
        if winner:
            draw_win_screen(screen)

        pygame.display.flip()


if __name__ == "__main__":
    main()