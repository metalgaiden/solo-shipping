import random
from typing import Tuple

import numpy as np

import tile_types


class RectangularRoom:
    def __init__(self, x: int, y: int, width: int, height: int):
        self.x1 = x
        self.y1 = y
        self.x2 = x + width
        self.y2 = y + height

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    @property
    def inner(self):
        """Slice covering the floor area (excludes the outer wall)."""
        return np.s_[self.x1 + 1 : self.x2, self.y1 + 1 : self.y2]

    def intersects(self, other: "RectangularRoom") -> bool:
        return (
            self.x1 <= other.x2
            and self.x2 >= other.x1
            and self.y1 <= other.y2
            and self.y2 >= other.y1
        )


def _tunnel_between(
    start: Tuple[int, int], end: Tuple[int, int]
) -> list:
    """Return an L-shaped list of (x, y) points connecting two rooms."""
    x1, y1 = start
    x2, y2 = end
    points = []
    if random.random() < 0.5:
        # Horizontal then vertical
        for x in range(min(x1, x2), max(x1, x2) + 1):
            points.append((x, y1))
        for y in range(min(y1, y2), max(y1, y2) + 1):
            points.append((x2, y))
    else:
        # Vertical then horizontal
        for y in range(min(y1, y2), max(y1, y2) + 1):
            points.append((x1, y))
        for x in range(min(x1, x2), max(x1, x2) + 1):
            points.append((x, y2))
    return points


SPELL_COLORS = {
    "passwall": (180,  80, 220),   # purple
    "camo":     ( 50, 200, 180),   # teal
    "decoy":    (220, 160,  30),   # amber
    "silence":  ( 70, 110, 220),   # blue
}


class Pickup:
    def __init__(self, x: int, y: int, spell: str, charges: int):
        self.x = x
        self.y = y
        self.spell = spell
        self.charges = charges


class GameMap:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.tiles = np.full(
            (width, height), fill_value=tile_types.WALL, dtype=tile_types.tile_dt
        )
        self.rooms: list = []
        self.noisy_tiles: set = set()  # (x, y) positions that make noise when stepped on
        self.pickup: Pickup | None = None

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and bool(self.tiles[x, y]["walkable"])

    def trigger_noise(self, x: int, y: int) -> bool:
        """If (x, y) is a noisy tile, consume it and return True."""
        if (x, y) in self.noisy_tiles:
            self.noisy_tiles.discard((x, y))
            return True
        return False

    def render(self, console) -> None:
        console.tiles_rgb[0 : self.width, 0 : self.height] = self.tiles["dark"]
        # Noisy tiles are tinted tan so the player has a chance to spot them
        for x, y in self.noisy_tiles:
            console.print(x, y, ".", fg=(170, 130, 60))
        if self.pickup:
            color = SPELL_COLORS.get(self.pickup.spell, (200, 200, 200))
            console.print(self.pickup.x, self.pickup.y, "*", fg=color)


def _gen_classic(
    dungeon: "GameMap",
    max_rooms: int,
    room_min_size: int,
    room_max_size: int,
) -> list:
    """Random rectangular rooms connected by L-shaped corridors."""
    rooms: list[RectangularRoom] = []
    for _ in range(max_rooms):
        room_w = random.randint(room_min_size, room_max_size)
        room_h = random.randint(room_min_size, room_max_size)
        x = random.randint(0, dungeon.width - room_w - 1)
        y = random.randint(0, dungeon.height - room_h - 1)

        new_room = RectangularRoom(x, y, room_w, room_h)
        if any(new_room.intersects(r) for r in rooms):
            continue

        dungeon.tiles[new_room.inner] = tile_types.FLOOR

        if rooms:
            for px, py in _tunnel_between(rooms[-1].center, new_room.center):
                dungeon.tiles[px, py] = tile_types.FLOOR

        rooms.append(new_room)
    return rooms


def _gen_drunk_walk(dungeon: "GameMap") -> list:
    """Drunkard's walk: momentum-biased walkers carve organic corridors.

    Anchor rooms are dropped every WAYPOINT_EVERY steps and used as
    spawn / pickup points by the rest of the engine.
    """
    NUM_WALKERS    = 3
    FLOOR_TARGET   = 0.38   # stop once ~38 % of tiles are floor
    MOMENTUM       = 0.78   # chance to keep current direction
    WAYPOINT_EVERY = 22     # drop an anchor room every N steps
    ANCHOR_SIZE    = 5      # side length of carved anchor rooms

    map_width, map_height = dungeon.width, dungeon.height
    total_tiles  = map_width * map_height
    target_floor = int(total_tiles * FLOOR_TARGET)
    floor_count  = 0

    cx, cy = map_width // 2, map_height // 2
    waypoints: list[tuple[int, int]] = [(cx, cy)]   # centre is always first anchor

    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    for walker_idx in range(NUM_WALKERS):
        if floor_count >= target_floor:
            break

        # Walker 0 always starts at the map centre so the rooms[0] anchor is
        # guaranteed to sit on the carved path and be reachable by the player.
        if walker_idx == 0:
            wx, wy = cx, cy
        else:
            wx = cx + random.randint(-map_width // 5, map_width // 5)
            wy = cy + random.randint(-map_height // 5, map_height // 5)
            wx = max(2, min(map_width - 3, wx))
            wy = max(2, min(map_height - 3, wy))

        direction = random.choice(dirs)
        steps_since_waypoint = 0

        for _ in range(total_tiles * 3):
            if floor_count >= target_floor:
                break

            if not dungeon.tiles[wx, wy]["walkable"]:
                dungeon.tiles[wx, wy] = tile_types.FLOOR
                floor_count += 1

            steps_since_waypoint += 1
            if steps_since_waypoint >= WAYPOINT_EVERY:
                waypoints.append((wx, wy))
                steps_since_waypoint = 0

            if random.random() > MOMENTUM:
                direction = random.choice(dirs)

            nx, ny = wx + direction[0], wy + direction[1]
            if 1 <= nx < map_width - 1 and 1 <= ny < map_height - 1:
                wx, wy = nx, ny
            else:
                direction = random.choice(dirs)

    # Build anchor rooms at each recorded waypoint.
    rooms: list[RectangularRoom] = []
    half = ANCHOR_SIZE // 2
    for wpx, wpy in waypoints:
        room = RectangularRoom(wpx - half, wpy - half, ANCHOR_SIZE, ANCHOR_SIZE)
        if (
            room.x1 >= 1
            and room.y1 >= 1
            and room.x2 < map_width
            and room.y2 < map_height
            and not any(room.intersects(r) for r in rooms)
        ):
            dungeon.tiles[room.inner] = tile_types.FLOOR
            rooms.append(room)
    return rooms


def _connected_rooms(dungeon: "GameMap", rooms: list) -> list:
    """Flood-fill from rooms[0].center and return only reachable rooms.

    Guarantees that every room in the returned list can be walked to from the
    player's starting position, so the goal and patrol rooms are always reachable.
    """
    if not rooms:
        return rooms
    sx, sy = rooms[0].center
    visited: set = {(sx, sy)}
    stack = [(sx, sy)]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if (nx, ny) not in visited and dungeon.is_walkable(nx, ny):
                visited.add((nx, ny))
                stack.append((nx, ny))
    return [r for r in rooms if r.center in visited]


def generate_dungeon(
    map_width: int,
    map_height: int,
    max_rooms: int = 30,
    room_min_size: int = 6,
    room_max_size: int = 10,
) -> Tuple["GameMap", Tuple[int, int]]:
    # Retry until we get a connected map with at least 2 reachable rooms
    # (player start + at least one goal candidate).  In practice the first
    # attempt almost always succeeds; the loop is a safety net.
    dungeon = GameMap(map_width, map_height)
    rooms: list = []
    for _ in range(10):
        dungeon = GameMap(map_width, map_height)
        if random.random() < 0.5:
            rooms = _gen_classic(dungeon, max_rooms, room_min_size, room_max_size)
        else:
            rooms = _gen_drunk_walk(dungeon)
        rooms = _connected_rooms(dungeon, rooms)
        if len(rooms) >= 2:
            break

    # ------------------------------------------------------------------ #
    # Shared post-generation logic                                         #
    # ------------------------------------------------------------------ #
    dungeon.rooms = rooms

    # Place a spell pickup in a middle room (not start or goal).
    pickup_pool = rooms[1:-1] if len(rooms) > 2 else rooms[1:] if len(rooms) > 1 else rooms
    if pickup_pool:
        pickup_room = random.choice(pickup_pool)
        spell = random.choice(list(SPELL_COLORS))
        dungeon.pickup = Pickup(*pickup_room.center, spell=spell, charges=2)

    player_start = rooms[0].center if rooms else (map_width // 2, map_height // 2)

    # Scatter noisy tiles across ~1/6 of walkable floor tiles.
    # Exclude a small buffer around the player's start so they aren't
    # immediately alerted on the first step.
    ps_x, ps_y = player_start
    walkable_xs, walkable_ys = np.where(dungeon.tiles["walkable"])
    candidates = [
        (int(wx), int(wy))
        for wx, wy in zip(walkable_xs, walkable_ys)
        if abs(wx - ps_x) > 4 or abs(wy - ps_y) > 4
    ]
    noise_count = max(1, len(candidates) // 6)
    if candidates:
        dungeon.noisy_tiles = set(
            random.sample(candidates, min(noise_count, len(candidates)))
        )

    return dungeon, player_start

# --- To test ---
# cd roguelike-game && python main.py
#
# Each new level randomly picks one of two generators (50 / 50):
#
#   _gen_classic     — scattered rectangular rooms connected by L-shaped corridors.
#                      Feels like a traditional dungeon; lots of dead-end pockets.
#
#   _gen_drunk_walk  — momentum-biased random walkers carve organic corridors.
#                      Feels open and winding; small anchor rooms mark key spots.
#
# Both methods produce a dungeon.rooms list so all downstream logic
# (player start, pickup placement, noisy tiles) works identically.
