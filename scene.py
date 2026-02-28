"""
Visual novel scene player for Solo's Adventures in Shipping.

Dialogue files use a simple line-based format:

    # This is a comment — ignored.
    SOLO: Line of dialogue here.
    BIG_BOSS: Another line here.

Blank lines are also ignored.
Supported speaker keys: SOLO, BIG_BOSS
"""
import os
import sys
import textwrap
from typing import List, Tuple

import tcod
import tcod.event

from logger import log

# ------------------------------------------------------------------ #
#  Screen dimensions (must match main.py)                             #
# ------------------------------------------------------------------ #

SCREEN_WIDTH  = 80
SCREEN_HEIGHT = 50

# ------------------------------------------------------------------ #
#  Portrait frame layout                                              #
# ------------------------------------------------------------------ #

PORT_INNER_W = 20    # portrait content width
PORT_INNER_H = 16    # portrait content height
PORT_FRAME_W = 22    # PORT_INNER_W + 2
PORT_FRAME_H = 18    # PORT_INNER_H + 2

LEFT_FRAME_X  = 2
LEFT_FRAME_Y  = 2
RIGHT_FRAME_X = 56   # SCREEN_WIDTH - PORT_FRAME_W - 2
RIGHT_FRAME_Y = 2

NAME_ROW = 21        # LEFT_FRAME_Y + PORT_FRAME_H + 1

# ------------------------------------------------------------------ #
#  Dialogue box layout                                                #
# ------------------------------------------------------------------ #

BOX_X  = 1
BOX_Y  = 26
BOX_W  = 78          # SCREEN_WIDTH - 2
BOX_H  = 24          # SCREEN_HEIGHT - BOX_Y

TEXT_X    = 3
TEXT_Y    = 29       # BOX_Y + 3
TEXT_W    = 74       # BOX_W - 4
MAX_LINES = 4

# ------------------------------------------------------------------ #
#  Character display config                                           #
# ------------------------------------------------------------------ #

CHAR_COLORS: dict[str, Tuple[int, int, int]] = {
    "SOLO":     (220, 220, 220),
    "BIG_BOSS": (220,  80,  60),
}

CHAR_DISPLAY: dict[str, str] = {
    "SOLO":     "Solo",
    "BIG_BOSS": "Big Boss",
}

DIM_COLOR: Tuple[int, int, int] = (40, 40, 50)

# ------------------------------------------------------------------ #
#  ASCII portraits (PORT_INNER_W cols × PORT_INNER_H rows)           #
#  Each line must be ≤ PORT_INNER_W (20) characters.                 #
# ------------------------------------------------------------------ #

PORTRAITS: dict[str, List[str]] = {
    "SOLO": [
        "   ______________   ",
        "  / ____________ \\  ",
        " / /  *      *  \\ \\ ",
        "| |   ________   | |",
        "| |  |        |  | |",
        "| |  |________|  | |",
        " \\ \\            / / ",
        "  '\\____________'/ ",
        "    |          |   ",
        "  __|          |__ ",
        " /  |          |  \\",
        "/   |          |   \\",
        "|   |          |   |",
        "|   |          |   |",
        " \\  |          |  / ",
        "  \\_|__________|_/ ",
    ],
    "BIG_BOSS": [
        "    ____________    ",
        "   [____________]   ",
        "  /              \\  ",
        " | [X]      . .  | ",
        " |   __________  | ",
        " |  |          | | ",
        " |  |__________| | ",
        "  \\              /  ",
        "   |          |    ",
        "  __|          |__ ",
        " /  |          |  \\",
        "/   |          |   \\",
        "|   |          |   |",
        "|   |          |   |",
        " \\  |          |  / ",
        "  \\_|__________|_/ ",
    ],
}


# ------------------------------------------------------------------ #
#  Asset path helper (mirrors main.py — supports PyInstaller bundles) #
# ------------------------------------------------------------------ #

def _asset(filename: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


# ------------------------------------------------------------------ #
#  Parser                                                              #
# ------------------------------------------------------------------ #

def parse_scene(filepath: str) -> List[Tuple[str, str]]:
    """Read a dialogue file and return a list of (speaker_key, text) tuples.

    Returns an empty list if the file is missing or contains no valid lines.
    """
    if not os.path.exists(filepath):
        log.warning(f"Dialogue file not found: {filepath}")
        return []

    lines = []
    with open(filepath, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                speaker, _, text = line.partition(":")
                key = speaker.strip().upper().replace(" ", "_")
                lines.append((key, text.strip()))
    return lines


# ------------------------------------------------------------------ #
#  Renderer                                                            #
# ------------------------------------------------------------------ #

def _draw_portrait_frame(
    console,
    fx: int,
    fy: int,
    portrait_lines: List[str],
    frame_color: Tuple[int, int, int],
    art_color: Tuple[int, int, int],
) -> None:
    """Draw a framed portrait at (fx, fy) with the given art and colors."""
    console.draw_frame(fx, fy, PORT_FRAME_W, PORT_FRAME_H, fg=frame_color, bg=(0, 0, 0))
    for i, line in enumerate(portrait_lines[:PORT_INNER_H]):
        console.print(fx + 1, fy + 1 + i, line, fg=art_color, bg=(0, 0, 0))


def _render_codec(
    console,
    active_key: str,
    display_name: str,
    name_color: Tuple[int, int, int],
    text_lines: List[str],
) -> None:
    """Render the full-screen codec dialogue layout."""
    console.clear(fg=(255, 255, 255), bg=(0, 0, 0))

    # Active speaker gets their character color; inactive speaker goes dim
    bb_color   = CHAR_COLORS["BIG_BOSS"] if active_key == "BIG_BOSS" else DIM_COLOR
    solo_color = CHAR_COLORS["SOLO"]     if active_key != "BIG_BOSS" else DIM_COLOR

    # Left portrait — BIG_BOSS
    _draw_portrait_frame(
        console,
        LEFT_FRAME_X, LEFT_FRAME_Y,
        PORTRAITS["BIG_BOSS"],
        bb_color, bb_color,
    )
    bb_label   = CHAR_DISPLAY.get("BIG_BOSS", "Big Boss")
    bb_label_x = LEFT_FRAME_X + (PORT_FRAME_W - len(bb_label)) // 2
    console.print(bb_label_x, NAME_ROW, bb_label, fg=bb_color, bg=(0, 0, 0))

    # Right portrait — SOLO
    _draw_portrait_frame(
        console,
        RIGHT_FRAME_X, RIGHT_FRAME_Y,
        PORTRAITS["SOLO"],
        solo_color, solo_color,
    )
    solo_label   = CHAR_DISPLAY.get("SOLO", "Solo")
    solo_label_x = RIGHT_FRAME_X + (PORT_FRAME_W - len(solo_label)) // 2
    console.print(solo_label_x, NAME_ROW, solo_label, fg=solo_color, bg=(0, 0, 0))

    # Dialogue box
    console.draw_frame(BOX_X, BOX_Y, BOX_W, BOX_H, fg=(80, 80, 110), bg=(10, 10, 20))

    # Speaker name
    console.print(TEXT_X, BOX_Y + 1, display_name, fg=name_color, bg=(10, 10, 20))

    # Horizontal divider under the name
    console.print(TEXT_X, BOX_Y + 2, "\u2500" * TEXT_W, fg=(50, 50, 70), bg=(10, 10, 20))

    # Dialogue text
    for i, line in enumerate(text_lines):
        console.print(TEXT_X, TEXT_Y + i, line, fg=(200, 200, 200), bg=(10, 10, 20))

    # Continue prompt (right-aligned within the box)
    prompt = "[Enter / Space]"
    console.print(
        BOX_X + BOX_W - len(prompt) - 2,
        BOX_Y + BOX_H - 2,
        prompt,
        fg=(90, 90, 120), bg=(10, 10, 20),
    )


def _wait_for_keypress(context) -> None:
    """Block until the player presses any key (or quits)."""
    while True:
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                return


def play_scene(console, context, filepath: str) -> None:
    """Display a full dialogue scene, one beat at a time.

    Each line in the file is one beat; long lines are word-wrapped and
    paginated so no text is ever clipped.
    """
    lines = parse_scene(filepath)
    if not lines:
        return

    for speaker_key, text in lines:
        name_color   = CHAR_COLORS.get(speaker_key, (200, 200, 200))
        display_name = CHAR_DISPLAY.get(
            speaker_key, speaker_key.replace("_", " ").title()
        )

        wrapped = textwrap.wrap(text, width=TEXT_W) or [""]

        # Paginate in chunks of MAX_LINES
        for page_start in range(0, len(wrapped), MAX_LINES):
            page_lines = wrapped[page_start : page_start + MAX_LINES]

            _render_codec(console, speaker_key, display_name, name_color, page_lines)

            context.present(console)
            _wait_for_keypress(context)
