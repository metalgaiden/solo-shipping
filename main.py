#!/usr/bin/env python3
import os
import random
import sys
import time
import audio
from typing import Tuple


def _asset(filename: str) -> str:
    """Resolve a bundled asset path for both normal runs and PyInstaller builds."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)

import tcod
import tcod.event
import tcod.map

from enemy import Enemy, Mode, SIGHT_RADIUS, _compute_path
from game_map import GameMap, generate_dungeon, SPELL_COLORS
from logger import log
from scene import play_scene

SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50
TITLE = "Roguelike"
NUM_ENEMIES = 3

MOVE_KEYS = {
    # Wait in place
    tcod.event.KeySym.SPACE: (0,  0),
    tcod.event.KeySym.KP_5:  (0,  0),
    # Arrow keys
    tcod.event.KeySym.UP:    (0, -1),
    tcod.event.KeySym.DOWN:  (0,  1),
    tcod.event.KeySym.LEFT:  (-1, 0),
    tcod.event.KeySym.RIGHT: ( 1, 0),
    # WASD
    tcod.event.KeySym.W: (0, -1),
    tcod.event.KeySym.S: (0,  1),
    tcod.event.KeySym.A: (-1, 0),
    tcod.event.KeySym.D: ( 1, 0),
    # QEZC diagonals
    tcod.event.KeySym.Q: (-1, -1),
    tcod.event.KeySym.E: ( 1, -1),
    tcod.event.KeySym.Z: (-1,  1),
    tcod.event.KeySym.C: ( 1,  1),
    # Numpad (including diagonals)
    tcod.event.KeySym.KP_8: (0, -1),
    tcod.event.KeySym.KP_2: (0,  1),
    tcod.event.KeySym.KP_4: (-1, 0),
    tcod.event.KeySym.KP_6: ( 1, 0),
    tcod.event.KeySym.KP_7: (-1, -1),
    tcod.event.KeySym.KP_9: ( 1, -1),
    tcod.event.KeySym.KP_1: (-1,  1),
    tcod.event.KeySym.KP_3: ( 1,  1),
}


# ------------------------------------------------------------------ #
#  Level creation                                                       #
# ------------------------------------------------------------------ #

def create_level() -> Tuple[GameMap, int, int, Tuple[int, int], list]:
    """Generate a new dungeon and return (map, player_x, player_y, goal, enemies)."""
    game_map, (player_x, player_y) = generate_dungeon(SCREEN_WIDTH, SCREEN_HEIGHT)
    rooms = game_map.rooms

    # Goal: pick the room whose centre is farthest from the player's start.
    # Exclude rooms[0] (player start) so goal is always in a different room.
    candidate_rooms = rooms[1:] if len(rooms) > 1 else rooms
    goal_room = max(
        candidate_rooms,
        key=lambda r: (r.center[0] - player_x) ** 2 + (r.center[1] - player_y) ** 2,
    )
    goal: Tuple[int, int] = goal_room.center

    # Patrol sections are built from rooms[1:] so no enemy starts in the
    # player's room (rooms[0]).
    # forbidden_tiles ensures patrol paths never step on the player's start tile.
    non_player_rooms = rooms[1:] if len(rooms) > 1 else rooms
    forbidden = {(player_x, player_y)}
    section_size = max(1, len(non_player_rooms) // NUM_ENEMIES)
    patrol_sections = [
        non_player_rooms[i * section_size : (i + 1) * section_size]
        for i in range(NUM_ENEMIES)
    ]
    # Last section absorbs any remainder
    if patrol_sections and len(non_player_rooms) % NUM_ENEMIES:
        patrol_sections[-1] = non_player_rooms[(NUM_ENEMIES - 1) * section_size :]

    enemies: list[Enemy] = []
    for i in range(min(NUM_ENEMIES, len(patrol_sections))):
        section = patrol_sections[i] or non_player_rooms
        sx, sy = section[0].center
        search_rooms = list(rooms)
        random.shuffle(search_rooms)
        enemies.append(Enemy(sx, sy, section, search_rooms, eid=i, forbidden_tiles=forbidden))

    log.info(
        f"Level generated — player at ({player_x},{player_y}), goal at {goal}, "
        f"{len(rooms)} rooms, {len(enemies)} enemies, "
        f"{len(game_map.noisy_tiles)} noisy tiles"
    )
    for e in enemies:
        log.info(f"  E{e.eid} spawned at ({e.x},{e.y}), patrol waypoints: {e.patrol_waypoints}")

    return game_map, player_x, player_y, goal, enemies


# ------------------------------------------------------------------ #
#  Rendering                                                            #
# ------------------------------------------------------------------ #

def render_all(
    console,
    game_map: GameMap,
    player_x: int,
    player_y: int,
    enemies: list,
    goal: Tuple[int, int],
    level: int,
    noise_warning: bool = False,
    active_spell: str | None = None,
    spell_charges: int = 0,
    passwall_primed: bool = False,
    camo_active: bool = False,
    decoy_primed: bool = False,
    mouse_tile: Tuple[int, int] | None = None,
    silence_steps: int = 0,
) -> None:
    console.clear()
    game_map.render(console)

    # Vision cones — tint the background of every floor tile each enemy can see
    for enemy in enemies:
        tint = (55, 10, 10) if enemy.mode == Mode.SEARCH else (45, 30, 5)
        fov = enemy.fov_array(game_map) & game_map.tiles["walkable"]
        console.rgb["bg"][fov] = tint

    # Goal tile
    console.print(goal[0], goal[1], ">", fg=(50, 255, 100))

    # Enemies
    for enemy in enemies:
        console.print(enemy.x, enemy.y, "E", fg=enemy.color)

    # Player (shown as a rock while camo is active)
    if camo_active:
        console.print(player_x, player_y, "o", fg=(150, 150, 150))
    else:
        console.print(player_x, player_y, "@", fg=(255, 255, 255))

    # Decoy targeting crosshair — drawn last so it appears on top of everything
    if decoy_primed and mouse_tile is not None and game_map.in_bounds(*mouse_tile):
        console.print(mouse_tile[0], mouse_tile[1], "+", fg=(220, 160, 30))

    # HUD — level on line 0, noise warning on line 1 (shown for a few turns)
    console.print(1, 0, f"Level {level}", fg=(200, 200, 200), bg=(0, 0, 0))
    if noise_warning:
        console.print(1, 1, "! Your footsteps echo !", fg=(255, 200, 50), bg=(0, 0, 0))

    # Spell HUD — bottom of screen (hidden until a spell is picked up)
    if active_spell is not None:
        base_colors = {"passwall": (180, 80, 220), "camo": (50, 200, 180), "decoy": (220, 160, 30), "silence": (70, 110, 220), "flash": (255, 240, 80), "swap": (100, 255, 160)}
        if passwall_primed:
            color = (255, 230, 60)
            label = f"[F] {active_spell.capitalize()}  x{spell_charges}  [ready]"
        elif camo_active:
            color = (80, 255, 220)
            label = f"[F] {active_spell.capitalize()}  x{spell_charges}  [active]"
        elif decoy_primed:
            color = (255, 210, 60)
            label = f"[F] {active_spell.capitalize()}  x{spell_charges}  [click to place]"
        elif silence_steps > 0:
            color = (140, 180, 255)
            label = f"[F] {active_spell.capitalize()}  x{spell_charges}  [active]"
        else:
            color = base_colors.get(active_spell, (200, 200, 200))
            label = f"[F] {active_spell.capitalize()}  x{spell_charges}"
        console.print(1, SCREEN_HEIGHT - 1, label, fg=color, bg=(0, 0, 0))


# ------------------------------------------------------------------ #
#  Overlay messages                                                     #
# ------------------------------------------------------------------ #

def _overlay_message(console, context, msg: str, fg: Tuple[int, int, int]) -> None:
    """Print a centred message and wait for any keypress."""
    x = max(0, (SCREEN_WIDTH - len(msg)) // 2)
    y = SCREEN_HEIGHT // 2
    console.print(x, y, msg, fg=fg, bg=(0, 0, 0))
    context.present(console)
    while True:
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                return


def show_caught_message(
    console, context, game_map, player_x, player_y, enemies, goal, level,
    noise_warning=False, active_spell=None, spell_charges=0,
    passwall_primed=False, camo_active=False,
) -> None:
    render_all(console, game_map, player_x, player_y, enemies, goal, level,
               noise_warning, active_spell, spell_charges, passwall_primed, camo_active)
    _overlay_message(console, context, " You were caught!  Press any key to continue. ", (255, 200, 50))


def show_level_complete(console, context, level: int) -> None:
    _overlay_message(console, context, f" Level {level} complete!  Press any key to continue. ", (100, 220, 255))


def show_help_screen(console, context) -> None:
    """Display a controls and spell reference. Any key returns to the title."""
    GOLD   = (220, 190,  80)
    HEAD   = (190, 190, 190)
    DIM    = (120, 120, 120)
    BRIGHT = (210, 210, 210)

    while True:
        console.clear()

        heading = "Controls & Spells"
        console.print((SCREEN_WIDTH - len(heading)) // 2, 2, heading, fg=GOLD)

        # ── Movement ─────────────────────────────────────────────────
        console.print(4, 5, "MOVEMENT", fg=HEAD)
        bindings = [
            ("Arrow keys / WASD / Numpad 8426", "Move"),
            ("Q, E, Z, C / Numpad 7, 9, 1, 3", "Move diagonally"),
            ("Space / Numpad 5              ", "Wait one turn"),
            ("Esc                           ", "Quit"),
        ]
        for i, (keys, action) in enumerate(bindings):
            console.print(6,  6 + i, keys,   fg=BRIGHT)
            console.print(42, 6 + i, action, fg=DIM)

        # ── Spells ────────────────────────────────────────────────────
        console.print(4, 12, "SPELLS", fg=HEAD)
        console.print(6, 13, "Pick up a  *  to gain a spell.  Press F to use.", fg=DIM)

        spells = [
            (
                "Passwall", (180, 80, 220),
                [
                    "Press F to prime, then step into a wall.",
                    "Teleports through walls of any thickness.",
                ],
            ),
            (
                "Camo", (50, 200, 180),
                [
                    "Press F to activate — guards can no longer see you.",
                    "Breaks the moment you take a step.",
                ],
            ),
            (
                "Decoy", (220, 160, 30),
                [
                    "Press F to prime, then left-click any tile.",
                    "Creates a noise that draws patrolling guards.",
                    "Moving cancels the aim.",
                ],
            ),
            (
                "Silence", (70, 110, 220),
                [
                    "Press F to activate.",
                    "Your footsteps make no noise for the rest of the level.",
                ],
            ),
            (
                "Flash", (255, 240, 80),
                [
                    "Press F to blind all guards in your line of sight.",
                    "Blinded guards cannot spot you for 20 turns.",
                ],
            ),
            (
                "Swap", (100, 255, 160),
                [
                    "Press F to instantly swap with the nearest guard in sight.",
                    "You take their position; they take yours.",
                ],
            ),
        ]

        y = 15
        for name, color, lines in spells:
            console.print(6, y, f"* {name}", fg=color)
            for j, line in enumerate(lines):
                console.print(10, y + 1 + j, line, fg=DIM)
            y += len(lines) + 2

        back = "[Any key]  Back"
        console.print((SCREEN_WIDTH - len(back)) // 2, SCREEN_HEIGHT - 2, back, fg=DIM)

        context.present(console)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return
            if isinstance(event, tcod.event.KeyDown):
                return


def show_title_screen(console, context) -> str:
    """Render the title screen. Returns 'start', 'quit', or 'demo'."""
    IDLE_TIMEOUT = 8.0
    TITLE_STR = "Solo's Adventures in Shipping"
    TAGLINE   = "a stealth roguelike"
    OPT_START = "[Enter]   Begin Mission"
    OPT_HELP  = "[H]       How to Play"
    OPT_EXIT  = "[Esc]     Exit"
    DEMO_HINT = "or wait to watch a demo"

    ty = SCREEN_HEIGHT // 3
    deadline = time.monotonic() + IDLE_TIMEOUT

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "demo"

        # Animate dots to signal the timer is running
        dot_count = int((IDLE_TIMEOUT - remaining) * 0.6) % 4
        hint = DEMO_HINT + "." * dot_count + " " * (3 - dot_count)

        console.clear()
        console.print(
            (SCREEN_WIDTH - len(TITLE_STR)) // 2, ty,
            TITLE_STR, fg=(220, 190, 80),
        )
        console.print(
            (SCREEN_WIDTH - len(TAGLINE)) // 2, ty + 2,
            TAGLINE, fg=(140, 140, 140),
        )
        console.print(
            (SCREEN_WIDTH - len(OPT_START)) // 2, ty + 6,
            OPT_START, fg=(210, 210, 210),
        )
        console.print(
            (SCREEN_WIDTH - len(OPT_HELP)) // 2, ty + 8,
            OPT_HELP, fg=(180, 180, 180),
        )
        console.print(
            (SCREEN_WIDTH - len(OPT_EXIT)) // 2, ty + 10,
            OPT_EXIT, fg=(160, 160, 160),
        )
        console.print(
            (SCREEN_WIDTH - len(DEMO_HINT) - 3) // 2, ty + 13,
            hint, fg=(90, 90, 90),
        )

        context.present(console)

        for event in tcod.event.get():
            if isinstance(event, tcod.event.Quit):
                return "quit"
            if isinstance(event, tcod.event.KeyDown):
                deadline = time.monotonic() + IDLE_TIMEOUT  # reset on any key
                if event.sym in (tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER):
                    return "start"
                if event.sym == tcod.event.KeySym.h:
                    show_help_screen(console, context)
                    deadline = time.monotonic() + IDLE_TIMEOUT
                if event.sym == tcod.event.KeySym.ESCAPE:
                    return "quit"

        time.sleep(0.05)  # ~20 fps polling — keeps the title screen responsive


# ------------------------------------------------------------------ #
#  Attract-mode demo                                                    #
# ------------------------------------------------------------------ #

def run_demo(console, context) -> None:
    """Play the game with a simple AI until the player presses any key."""
    STEP_INTERVAL = 0.18  # seconds between AI moves
    BANNER = "  DEMO \u2014 Press any key to play  "

    game_map, player_x, player_y, goal, enemies = create_level()
    last_step = time.monotonic()

    while True:
        # Exit on any keypress
        for event in tcod.event.get():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                return

        now = time.monotonic()
        if now - last_step >= STEP_INTERVAL:
            last_step = now

            # AI: flee from nearby guards, otherwise head to goal.
            # "Threatened" = any enemy within twice the sight radius.
            threatened = any(
                0 < len(_compute_path(game_map, e.x, e.y, player_x, player_y)) <= SIGHT_RADIUS + 2
                for e in enemies
            )
            if threatened:
                # Greedy flee: step to whichever adjacent walkable tile
                # maximises total squared distance from all enemies.
                # This guarantees the very next step moves away, unlike
                # pathfinding to a distant target whose route might pass
                # through the enemy first.
                def _flee_score(nx, ny):
                    return sum(
                        (e.x - nx) ** 2 + (e.y - ny) ** 2 for e in enemies
                    )
                best_pos = (player_x, player_y)
                best_score = _flee_score(player_x, player_y)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = player_x + dx, player_y + dy
                        if game_map.is_walkable(nx, ny):
                            s = _flee_score(nx, ny)
                            if s > best_score:
                                best_score = s
                                best_pos = (nx, ny)
                if best_pos != (player_x, player_y):
                    log.debug(
                        f"Demo AI flee: ({player_x},{player_y}) -> {best_pos}"
                    )
                player_x, player_y = best_pos
            else:
                path = _compute_path(game_map, player_x, player_y, *goal)
                if path:
                    player_x, player_y = path[0]

            # Trigger noise naturally so guards react as they would in real play
            if game_map.trigger_noise(player_x, player_y):
                for enemy in sorted(
                    enemies,
                    key=lambda e: (e.x - player_x) ** 2 + (e.y - player_y) ** 2,
                ):
                    enemy.alert_to_noise(player_x, player_y, game_map.rooms)

            # Enemy turns
            for enemy in enemies:
                enemy.take_turn(game_map, enemies)

            # Reset on caught or goal reached — just start a fresh level silently
            caught = any(
                not e.blinded_turns and e.can_see_player(player_x, player_y, game_map)
                for e in enemies
            )
            if caught or (player_x, player_y) == goal:
                game_map, player_x, player_y, goal, enemies = create_level()

        render_all(console, game_map, player_x, player_y, enemies, goal, level=1)
        console.print(
            (SCREEN_WIDTH - len(BANNER)) // 2,
            SCREEN_HEIGHT - 1,
            BANNER,
            fg=(255, 220, 60),
            bg=(0, 0, 0),
        )
        context.present(console)


# ------------------------------------------------------------------ #
#  Main                                                                 #
# ------------------------------------------------------------------ #
audio.init_audio()
audio.play_bgm()

def main() -> None:
    tileset = tcod.tileset.load_tilesheet(
        _asset("dejavu10x10_gs_tc.png"), 32, 8, tcod.tileset.CHARMAP_TCOD
    )

    with tcod.context.new(
        columns=SCREEN_WIDTH,
        rows=SCREEN_HEIGHT,
        tileset=tileset,
        title=TITLE,
        vsync=True,
    ) as context:
        console = tcod.console.Console(SCREEN_WIDTH, SCREEN_HEIGHT, order="F")

        while True:
            result = show_title_screen(console, context)
            if result == "quit":
                return
            if result == "demo":
                run_demo(console, context)
                continue
            break  # "start"

        play_scene(console, context, _asset(os.path.join("dialogue", "intro.txt")))

        level = 1
        log.info("=== Game started ===")
        game_map, player_x, player_y, goal, enemies = create_level()
        noise_warning_turns = 0

        # Spell state — persists across level resets
        # Start each new game with one charge of a random spell.
        active_spell: str | None = random.choice(list(SPELL_COLORS))
        spell_charges: int = 1
        passwall_primed: bool = False
        camo_active: bool = False
        decoy_primed: bool = False
        silence_steps: int = 0
        moved_diagonally: int = 0
        mouse_tile: Tuple[int, int] | None = None

        while True:
            render_all(
                console, game_map, player_x, player_y, enemies, goal, level,
                noise_warning=noise_warning_turns > 0,
                active_spell=active_spell, spell_charges=spell_charges,
                passwall_primed=passwall_primed, camo_active=camo_active,
                decoy_primed=decoy_primed, mouse_tile=mouse_tile,
                silence_steps=silence_steps,
            )
            context.present(console)

            for event in tcod.event.wait():
                context.convert_event(event)

                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()

                if isinstance(event, tcod.event.MouseMotion):
                    mouse_tile = (int(event.tile.x), int(event.tile.y))

                if isinstance(event, tcod.event.MouseButtonDown):
                    log.debug(f"MouseButtonDown: btn={event.button} decoy={decoy_primed} mouse_tile={mouse_tile}")
                    if decoy_primed and event.button == tcod.event.MouseButton.LEFT:
                        if mouse_tile is not None and game_map.in_bounds(*mouse_tile):
                            nx, ny = mouse_tile
                            for enemy in enemies:
                                enemy.alert_to_noise(nx, ny, game_map.rooms)
                            spell_charges -= 1
                            audio.play_sfx('magic')
                            log.info(f"Decoy noise at ({nx},{ny}) — charges remaining: {spell_charges}")
                        else:
                            log.debug(f"Decoy placement failed: mouse_tile={mouse_tile}")
                        decoy_primed = False
                        # Decoy use is a player action — enemies take a turn
                        for enemy in enemies:
                            enemy.take_turn(game_map, enemies)
                        spotter = None if camo_active else next(
                            (e for e in enemies if not e.blinded_turns and e.can_see_player(player_x, player_y, game_map)),
                            None,
                        )
                        if spotter is not None:
                            log.warning(f"E{spotter.eid} spotted player after decoy — resetting level {level}")
                            spotter.mode = Mode.SEARCH
                            show_caught_message(
                                console, context, game_map,
                                player_x, player_y, enemies, goal, level,
                                noise_warning=noise_warning_turns > 0,
                                active_spell=active_spell, spell_charges=spell_charges,
                                passwall_primed=passwall_primed, camo_active=camo_active,
                            )
                            level = 1
                            active_spell = random.choice(list(SPELL_COLORS))
                            spell_charges = 1
                            game_map, player_x, player_y, goal, enemies = create_level()
                            noise_warning_turns = 0
                            passwall_primed = False
                            camo_active = False
                            decoy_primed = False
                            silence_steps = 0
                            moved_diagonally = 0
                            break

                if isinstance(event, tcod.event.KeyDown):
                    if event.sym == tcod.event.KeySym.ESCAPE:
                        show_help_screen(console, context)
                        break

                    # if event.sym == tcod.event.KeySym.r:
                    #     log.info("Manual reset")
                    #     level = 1
                    #     active_spell = random.choice(list(SPELL_COLORS))
                    #     spell_charges = 1
                    #     game_map, player_x, player_y, goal, enemies = create_level()
                    #     noise_warning_turns = 0
                    #     passwall_primed = False
                    #     camo_active = False
                    #     decoy_primed = False
                    #     silence_steps = 0
                    #     flash_primed = False
                    #     moved_diagonally = 0
                    #     break

                    if event.sym == tcod.event.KeySym.F:
                        try:
                            import audio
                        except Exception:
                            pass

                        if active_spell == "passwall" and spell_charges > 0:
                            passwall_primed = not passwall_primed
                            log.debug(f"Passwall {'primed' if passwall_primed else 'cancelled'}")
                        elif active_spell == "camo":
                            if camo_active:
                                camo_active = False
                                log.debug("Camo cancelled")
                            elif spell_charges > 0:
                                camo_active = True
                                audio.play_sfx('magic')
                                spell_charges -= 1
                                log.info(f"Camo activated — charges remaining: {spell_charges}")
                        elif active_spell == "decoy" and spell_charges > 0:
                            decoy_primed = not decoy_primed
                            log.debug(f"Decoy {'primed' if decoy_primed else 'cancelled'}")
                        elif active_spell == "silence" and spell_charges > 0 and silence_steps == 0:
                            audio.play_sfx('magic')
                            silence_steps = 1
                            spell_charges -= 1
                            log.info(f"Silence activated — charges remaining: {spell_charges}")
                        elif active_spell == "flash" and spell_charges > 0:
                            audio.play_sfx('magic')
                            player_fov = tcod.map.compute_fov(
                                game_map.tiles["transparent"].astype(bool),
                                (player_x, player_y),
                                radius=0,
                            )
                            targets = [e for e in enemies if player_fov[e.x, e.y]]
                            if targets:
                                for e in targets:
                                    e.blinded_turns = 20
                                spell_charges -= 1
                                log.info(f"Flash fired — blinded {len(targets)} enemies, charges remaining: {spell_charges}")
                        elif active_spell == "swap" and spell_charges > 0:
                            player_fov = tcod.map.compute_fov(
                                game_map.tiles["transparent"].astype(bool),
                                (player_x, player_y),
                                radius=0,  # 0 = unlimited — pure line of sight, no range cap
                            )
                            visible = [e for e in enemies if player_fov[e.x, e.y]]
                            if visible:
                                target = min(visible, key=lambda e: (e.x - player_x) ** 2 + (e.y - player_y) ** 2)
                                px, py = player_x, player_y
                                player_x, player_y = target.x, target.y
                                target.x, target.y = px, py
                                target._path = []
                                target._path_target = None
                                if target.mode == Mode.PATROL:
                                    target._start_search_at(game_map.rooms, noise_pos=(player_x, player_y))
                                audio.play_sfx('magic')
                                spell_charges -= 1
                                log.info(f"Swap used with E{target.eid} — player now at ({player_x},{player_y}), charges remaining: {spell_charges}")

                    if event.sym in MOVE_KEYS:
                        dx, dy = MOVE_KEYS[event.sym]
                        new_x = player_x + dx
                        new_y = player_y + dy

                        # Any directional move cancels decoy targeting
                        if dx != 0 or dy != 0:
                            decoy_primed = False

                        # Passwall: scan in the move direction for the first walkable tile
                        if passwall_primed and (dx != 0 or dy != 0) and not game_map.is_walkable(new_x, new_y):
                            dest = None
                            step = 2
                            while True:
                                tx, ty = player_x + step * dx, player_y + step * dy
                                if not game_map.in_bounds(tx, ty):
                                    break
                                if game_map.is_walkable(tx, ty):
                                    dest = (tx, ty)
                                    break
                                step += 1
                            if dest:
                                wall_thickness = step - 1
                                player_x, player_y = dest
                                spell_charges -= 1
                                moved = True
                                audio.play_sfx('magic')
                                log.info(f"Passwall used ({wall_thickness}-tile wall) — charges remaining: {spell_charges}")
                            else:
                                moved = False  # no floor found before map edge, spell fizzles
                            passwall_primed = False
                        else:
                            passwall_primed = False
                            moved = game_map.is_walkable(new_x, new_y)
                            if moved:
                                player_x, player_y = new_x, new_y

                        # Camo breaks the moment the player moves
                        if moved and (dx != 0 or dy != 0):
                            camo_active = False

                        # Track whether the player has ever moved diagonally
                        if moved and dx != 0 and dy != 0:
                            moved_diagonally += 1


                        # Pickup collection
                        if game_map.pickup and (player_x, player_y) == (game_map.pickup.x, game_map.pickup.y):
                            sp = game_map.pickup.spell
                            if active_spell != sp:
                                # Different spell — replace entirely
                                active_spell = sp
                                spell_charges = game_map.pickup.charges
                                passwall_primed = False
                                camo_active = False
                            else:
                                spell_charges += game_map.pickup.charges
                            log.info(f"Picked up {sp} x{game_map.pickup.charges} — {active_spell} x{spell_charges}")
                            game_map.pickup = None

                        # Goal reached → next level (or ending)
                        if (player_x, player_y) == goal:
                            log.info(f"Level {level} complete — player reached goal at ({player_x},{player_y})")
                            show_level_complete(console, context, level)
                            try:
                                import audio
                                audio.play_sfx('level_clear')
                            except Exception:
                                pass
                            if level >= 10:
                                if not moved_diagonally:
                                    play_scene(console, context, _asset(os.path.join("dialogue", "secret_ending.txt")))
                                else:
                                    diag_str = f"{moved_diagonally} time" if moved_diagonally == 1 else f"{moved_diagonally} times"
                                    play_scene(console, context, _asset(os.path.join("dialogue", "ending.txt")), variables={"diagonals": diag_str})
                                return  # game ends after level 10

                            level += 1

                            if level == 5:
                                play_scene(console, context, _asset(os.path.join("dialogue", "level_5.txt")))

                            game_map, player_x, player_y, goal, enemies = create_level()
                            noise_warning_turns = 0
                            passwall_primed = False
                            camo_active = False
                            decoy_primed = False
                            silence_steps = 0
                            break  # restart the render loop for the new level

                        # Noise — always consume the tile; silence suppresses the alert.
                        # alert_to_noise skips enemies already in search mode,
                        # so only patrolling enemies are affected.
                        # The HUD warning only appears if at least one enemy actually
                        # starts searching as a result.
                        if moved and game_map.trigger_noise(player_x, player_y):
                            if silence_steps > 0:
                                log.info(f"Noisy tile at ({player_x},{player_y}) suppressed by silence")
                            else:
                                log.info(f"Noisy tile triggered at ({player_x},{player_y})")
                                alerted = any(
                                    enemy.alert_to_noise(player_x, player_y, game_map.rooms)
                                    for enemy in sorted(
                                        enemies,
                                        key=lambda e: (e.x - player_x) ** 2 + (e.y - player_y) ** 2,
                                    )
                                )
                                if alerted:
                                    noise_warning_turns = 3

                        if noise_warning_turns > 0:
                            noise_warning_turns -= 1

                        # Enemy turns
                        for enemy in enemies:
                            enemy.take_turn(game_map, enemies)

                        # Caught check — camo and blinded enemies cannot spot the player
                        spotter = None if camo_active else next(
                            (e for e in enemies if not e.blinded_turns and e.can_see_player(player_x, player_y, game_map)),
                            None,
                        )
                        if spotter is not None:
                            log.warning(
                                f"E{spotter.eid} spotted player at ({player_x},{player_y}) "
                                f"— resetting level {level}"
                            )
                            try:
                                import audio
                                audio.play_sfx('game_over')
                            except Exception:
                                pass
                            spotter.mode = Mode.SEARCH  # render red on the caught frame
                            show_caught_message(
                                console, context, game_map,
                                player_x, player_y, enemies, goal, level,
                                noise_warning=noise_warning_turns > 0,
                                active_spell=active_spell, spell_charges=spell_charges,
                                passwall_primed=passwall_primed, camo_active=camo_active,
                            )
                            level = 1
                            active_spell = random.choice(list(SPELL_COLORS))
                            spell_charges = 1
                            game_map, player_x, player_y, goal, enemies = create_level()
                            noise_warning_turns = 0
                            passwall_primed = False
                            camo_active = False
                            decoy_primed = False
                            silence_steps = 0
                            moved_diagonally = 0
                            break


if __name__ == "__main__":
    main()
