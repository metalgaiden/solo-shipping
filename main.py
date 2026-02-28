#!/usr/bin/env python3
import os
import random
import sys
from typing import Tuple


def _asset(filename: str) -> str:
    """Resolve a bundled asset path for both normal runs and PyInstaller builds."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)

import tcod
import tcod.event

from enemy import Enemy, Mode
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
    # Arrow keys
    tcod.event.KeySym.UP:    (0, -1),
    tcod.event.KeySym.DOWN:  (0,  1),
    tcod.event.KeySym.LEFT:  (-1, 0),
    tcod.event.KeySym.RIGHT: ( 1, 0),
    # WASD
    tcod.event.KeySym.w: (0, -1),
    tcod.event.KeySym.s: (0,  1),
    tcod.event.KeySym.a: (-1, 0),
    tcod.event.KeySym.d: ( 1, 0),
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
    flash_primed: bool = False,
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
        base_colors = {"passwall": (180, 80, 220), "camo": (50, 200, 180), "decoy": (220, 160, 30), "silence": (70, 110, 220), "flash": (255, 240, 80)}
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
            label = f"[F] {active_spell.capitalize()}  x{spell_charges}  [silent - {silence_steps} steps]"
        elif flash_primed:
            color = (255, 255, 150)
            label = f"[F] {active_spell.capitalize()}  x{spell_charges}  [primed]"
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
            ("Numpad 7, 9, 1, 3             ", "Move diagonally"),
            ("Space                         ", "Wait one turn"),
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
                    "Teleports through walls 1-2 tiles thick.",
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
                    "Your next 10 steps make no noise.",
                ],
            ),
            (
                "Flash", (255, 240, 80),
                [
                    "Press F to prime, then step into a guard's sight.",
                    "Blinds every guard that can see you for 20 turns.",
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


def show_title_screen(console, context) -> bool:
    """Render the title screen. Returns True to start, False to quit."""
    TITLE     = "Solo's Adventures in Shipping"
    TAGLINE   = "a stealth roguelike"
    OPT_START = "[Enter]   Begin Mission"
    OPT_HELP  = "[H]       How to Play"
    OPT_EXIT  = "[Esc]     Exit"

    ty = SCREEN_HEIGHT // 3

    while True:
        console.clear()

        console.print(
            (SCREEN_WIDTH - len(TITLE)) // 2, ty,
            TITLE, fg=(220, 190, 80),
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

        context.present(console)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return False
            if isinstance(event, tcod.event.KeyDown):
                if event.sym in (tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER):
                    return True
                if event.sym == tcod.event.KeySym.h:
                    show_help_screen(console, context)
                if event.sym == tcod.event.KeySym.ESCAPE:
                    return False


# ------------------------------------------------------------------ #
#  Main                                                                 #
# ------------------------------------------------------------------ #

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

        if not show_title_screen(console, context):
            return

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
        flash_primed: bool = False
        mouse_tile: Tuple[int, int] | None = None

        while True:
            render_all(
                console, game_map, player_x, player_y, enemies, goal, level,
                noise_warning=noise_warning_turns > 0,
                active_spell=active_spell, spell_charges=spell_charges,
                passwall_primed=passwall_primed, camo_active=camo_active,
                decoy_primed=decoy_primed, mouse_tile=mouse_tile,
                silence_steps=silence_steps, flash_primed=flash_primed,
            )
            context.present(console)

            for event in tcod.event.wait():
                context.convert_event(event)

                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()

                if isinstance(event, tcod.event.MouseMotion):
                    mouse_tile = (int(event.position.x), int(event.position.y))

                if isinstance(event, tcod.event.MouseButtonDown):
                    if decoy_primed and event.button == tcod.event.MouseButton.LEFT:
                        nx, ny = int(event.position.x), int(event.position.y)
                        if game_map.in_bounds(nx, ny):
                            for enemy in enemies:
                                enemy.alert_to_noise(nx, ny, game_map.rooms)
                            spell_charges -= 1
                            log.info(f"Decoy noise at ({nx},{ny}) — charges remaining: {spell_charges}")
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
                            flash_primed = False
                            break

                if isinstance(event, tcod.event.KeyDown):
                    if event.sym == tcod.event.KeySym.ESCAPE:
                        raise SystemExit()

                    if event.sym == tcod.event.KeySym.f:
                        if active_spell == "passwall" and spell_charges > 0:
                            passwall_primed = not passwall_primed
                            log.debug(f"Passwall {'primed' if passwall_primed else 'cancelled'}")
                        elif active_spell == "camo":
                            if camo_active:
                                camo_active = False
                                log.debug("Camo cancelled")
                            elif spell_charges > 0:
                                camo_active = True
                                spell_charges -= 1
                                log.info(f"Camo activated — charges remaining: {spell_charges}")
                        elif active_spell == "decoy" and spell_charges > 0:
                            decoy_primed = not decoy_primed
                            log.debug(f"Decoy {'primed' if decoy_primed else 'cancelled'}")
                        elif active_spell == "silence" and spell_charges > 0 and silence_steps == 0:
                            silence_steps = 10
                            spell_charges -= 1
                            log.info(f"Silence activated — charges remaining: {spell_charges}")
                        elif active_spell == "flash" and spell_charges > 0:
                            flash_primed = not flash_primed
                            log.debug(f"Flash {'primed' if flash_primed else 'cancelled'}")

                    if event.sym in MOVE_KEYS:
                        dx, dy = MOVE_KEYS[event.sym]
                        new_x = player_x + dx
                        new_y = player_y + dy

                        # Any directional move cancels decoy targeting
                        if dx != 0 or dy != 0:
                            decoy_primed = False

                        # Passwall: pass through walls up to 2 tiles thick
                        if passwall_primed and (dx != 0 or dy != 0) and not game_map.is_walkable(new_x, new_y):
                            b2x, b2y = player_x + 2 * dx, player_y + 2 * dy
                            b3x, b3y = player_x + 3 * dx, player_y + 3 * dy
                            if game_map.is_walkable(b2x, b2y):
                                player_x, player_y = b2x, b2y   # 1-tile wall
                                spell_charges -= 1
                                moved = True
                                log.info(f"Passwall used (1-tile wall) — charges remaining: {spell_charges}")
                            elif game_map.is_walkable(b3x, b3y):
                                player_x, player_y = b3x, b3y   # 2-tile wall
                                spell_charges -= 1
                                moved = True
                                log.info(f"Passwall used (2-tile wall) — charges remaining: {spell_charges}")
                            else:
                                moved = False  # wall too thick, spell fizzles
                            passwall_primed = False
                        else:
                            passwall_primed = False
                            moved = game_map.is_walkable(new_x, new_y)
                            if moved:
                                player_x, player_y = new_x, new_y

                        # Camo breaks the moment the player moves
                        if moved and (dx != 0 or dy != 0):
                            camo_active = False

                        # Silence counts down on each actual step
                        if moved and (dx != 0 or dy != 0) and silence_steps > 0:
                            silence_steps -= 1
                            log.debug(f"Silence: {silence_steps} steps remaining")

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

                            if level >= 10:
                                play_scene(console, context, _asset(os.path.join("dialogue", "ending.txt")))
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
                            flash_primed = False
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
                                    for enemy in enemies
                                )
                                if alerted:
                                    noise_warning_turns = 3

                        if noise_warning_turns > 0:
                            noise_warning_turns -= 1

                        # Flash trigger — fires when primed and an enemy can see the player
                        if flash_primed and moved:
                            seeing = [e for e in enemies if e.can_see_player(player_x, player_y, game_map)]
                            if seeing:
                                for e in seeing:
                                    e.blinded_turns = 20
                                spell_charges -= 1
                                flash_primed = False
                                log.info(f"Flash fired — blinded {len(seeing)} enemies, charges remaining: {spell_charges}")

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
                            flash_primed = False
                            break


if __name__ == "__main__":
    main()
