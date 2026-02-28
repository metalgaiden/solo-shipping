import numpy as np

# Matches the dtype expected by console.tiles_rgb
graphic_dt = np.dtype([
    ("ch", np.int32),  # Unicode codepoint
    ("fg", "3B"),      # RGB foreground
    ("bg", "3B"),      # RGB background
])

tile_dt = np.dtype([
    ("walkable",    bool),
    ("transparent", bool),
    ("dark",        graphic_dt),  # Appearance when not in FOV
])


def new_tile(*, walkable: bool, transparent: bool, dark: tuple) -> np.ndarray:
    return np.array((walkable, transparent, dark), dtype=tile_dt)


FLOOR = new_tile(
    walkable=True,
    transparent=True,
    dark=(ord("."), (100, 100, 100), (0, 0, 0)),
)

WALL = new_tile(
    walkable=False,
    transparent=False,
    dark=(ord("#"), (150, 130, 80), (0, 0, 0)),
)
