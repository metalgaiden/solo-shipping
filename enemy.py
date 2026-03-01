import math
import random
from enum import Enum, auto
from typing import List, Set, Tuple

from logger import log

import numpy as np
import tcod.map
import tcod.path

SIGHT_RADIUS = 5
NOISE_ALERT_RADIUS  = 20   # enemy must be within this distance to hear a noise
NOISE_SEARCH_RADIUS = 20   # only rooms within this distance of the noise source are searched


class Mode(Enum):
    PATROL = auto()
    SEARCH = auto()


class Enemy:
    PATROL_COLOR = (210, 140, 40)   # amber
    SEARCH_COLOR  = (220,  50, 50)  # red

    def __init__(
        self,
        x: int,
        y: int,
        patrol_rooms: list,                  # RectangularRoom objects for the patrol loop
        search_rooms: list,                  # RectangularRoom objects for systematic search
        eid: int = 0,                        # numeric ID used in log messages
        forbidden_tiles: set | None = None,  # tiles the patrol path must never cross
    ):
        self.x = x
        self.y = y
        self.eid = eid
        self._forbidden_tiles: set = set(forbidden_tiles) if forbidden_tiles else set()

        # ---- patrol state ----
        # Fixed list of room centres visited in order, wrapping back to index 0
        self.patrol_waypoints = [r.center for r in patrol_rooms]
        self.patrol_idx = 0

        # ---- search state ----
        # _default_search_rooms is the full ordered list used after a patrol loop.
        # search_rooms is the active list for the current sweep (may be noise-limited).
        self._default_search_rooms = list(search_rooms)
        self.search_rooms: list = []
        self.search_idx = 0
        self.cleared_tiles: Set[Tuple[int, int]] = set()

        self.mode: Mode = Mode.PATROL
        self._path: List[Tuple[int, int]] = []
        self._path_target: Tuple[int, int] | None = None
        self._noise_pos: Tuple[int, int] | None = None
        self.blinded_turns: int = 0

    # ------------------------------------------------------------------ #
    #  Public interface                                                     #
    # ------------------------------------------------------------------ #

    @property
    def color(self) -> Tuple[int, int, int]:
        return self.SEARCH_COLOR if self.mode == Mode.SEARCH else self.PATROL_COLOR

    def fov_array(self, game_map) -> np.ndarray:
        """Return a boolean (width, height) array of tiles visible to this enemy."""
        radius = 1 if self.blinded_turns > 0 else SIGHT_RADIUS
        return _fov(game_map, self.x, self.y, radius=radius)

    def take_turn(self, game_map, all_enemies: list) -> None:
        if self.blinded_turns > 0:
            self.blinded_turns -= 1
        if self.mode == Mode.PATROL:
            self._patrol_turn(game_map)
        else:
            self._search_turn(game_map, all_enemies)

    def can_see_player(self, px: int, py: int, game_map) -> bool:
        radius = 1 if self.blinded_turns > 0 else SIGHT_RADIUS
        return bool(_fov(game_map, self.x, self.y, radius=radius)[px, py])

    def reset_to_patrol(self) -> None:
        """Force this enemy back to patrol mode (e.g. after spotting the player)."""
        self._return_to_patrol()

    def alert_to_noise(self, nx: int, ny: int, all_rooms: list) -> bool:
        """If the noise at (nx, ny) is within alert range, start a limited search.

        Returns True if this enemy actually transitions to search mode.
        """
        if self.mode != Mode.PATROL:
            log.debug(f"E{self.eid} heard noise at ({nx},{ny}) but is already searching — ignored")
            return False
        dist = _dist(self.x, self.y, nx, ny)
        if dist > NOISE_ALERT_RADIUS:
            log.debug(f"E{self.eid} too far from noise at ({nx},{ny}) — dist {dist:.1f} > {NOISE_ALERT_RADIUS}")
            return False
        nearby = [r for r in all_rooms if _dist(*r.center, nx, ny) <= NOISE_SEARCH_RADIUS]
        if not nearby:
            nearby = list(all_rooms)
        random.shuffle(nearby)
        log.info(f"E{self.eid} alerted by noise at ({nx},{ny}), dist={dist:.1f}, searching {len(nearby)} rooms")
        self._start_search_at(nearby, noise_pos=(nx, ny))
        return True

    # ------------------------------------------------------------------ #
    #  Patrol mode                                                          #
    # ------------------------------------------------------------------ #

    def _patrol_turn(self, game_map) -> None:
        if not self.patrol_waypoints:
            return

        target = self.patrol_waypoints[self.patrol_idx]

        # Arrived at the current waypoint — advance to the next one (wrapping)
        if (self.x, self.y) == target:
            self.patrol_idx = (self.patrol_idx + 1) % len(self.patrol_waypoints)
            self._path_target = None
            target = self.patrol_waypoints[self.patrol_idx]

        if self._path_target != target or not self._path:
            self._path = _compute_path(
                game_map, self.x, self.y, *target,
                forbidden=self._forbidden_tiles,
            )
            self._path_target = target

        if self._path:
            self.x, self.y = self._path.pop(0)

    def _start_search_at(self, rooms: list, noise_pos: Tuple[int, int] | None = None) -> None:
        """Begin a fresh search sweep of the given rooms."""
        self.mode = Mode.SEARCH
        self.search_rooms = rooms
        self.search_idx = 0
        self.cleared_tiles = set()
        self._path = []
        self._path_target = None
        self._noise_pos = noise_pos
        centers = [r.center for r in rooms]
        log.info(f"E{self.eid} SEARCH started — {len(rooms)} rooms: {centers}")

    # ------------------------------------------------------------------ #
    #  Search mode                                                          #
    # ------------------------------------------------------------------ #

    def _search_turn(self, game_map, all_enemies: list) -> None:
        # Record every visible floor tile
        self._scan(game_map)

        # Exchange intel with any enemy currently in sight
        for other in all_enemies:
            if other is not self:
                self._try_share(other, game_map)

        # Go directly to the noise source first
        if self._noise_pos is not None:
            if self._noise_pos in self.cleared_tiles:
                log.debug(f"E{self.eid} noise source {self._noise_pos} scanned — proceeding to rooms")
                self._noise_pos = None
                self._path = []
                self._path_target = None
            else:
                target = self._noise_pos
                if self._path_target != target or not self._path:
                    self._path = _compute_path(game_map, self.x, self.y, *target)
                    self._path_target = target
                if self._path:
                    self.x, self.y = self._path.pop(0)
                else:
                    # Can't path there; skip it
                    log.debug(f"E{self.eid} can't path to noise source {self._noise_pos} — skipping")
                    self._noise_pos = None
                return

        # Skip rooms whose tiles are all accounted for
        while (
            self.search_idx < len(self.search_rooms)
            and self._room_is_cleared(self.search_rooms[self.search_idx], game_map)
        ):
            self.search_idx += 1
            self._path_target = None

        # All rooms cleared — head back to patrol
        if self.search_idx >= len(self.search_rooms):
            log.info(f"E{self.eid} search complete — {len(self.cleared_tiles)} tiles cleared")
            self._return_to_patrol()
            return

        target = self.search_rooms[self.search_idx].center
        if self._path_target != target or not self._path:
            self._path = _compute_path(game_map, self.x, self.y, *target)
            self._path_target = target

        if self._path:
            self.x, self.y = self._path.pop(0)
        else:
            # Path is empty: either already at the target or it's unreachable.
            # Advance past this room so the enemy doesn't freeze here forever.
            log.debug(f"E{self.eid} stuck at room {self.search_idx} — skipping")
            self.search_idx += 1
            self._path_target = None

    def _return_to_patrol(self) -> None:
        """Transition back to patrol, resuming from the nearest patrol waypoint."""
        self.mode = Mode.PATROL
        self._path = []
        self._path_target = None
        self._noise_pos = None
        if self.patrol_waypoints:
            self.patrol_idx = min(
                range(len(self.patrol_waypoints)),
                key=lambda i: _dist(self.x, self.y, *self.patrol_waypoints[i]),
            )
        log.info(f"E{self.eid} PATROL resumed at ({self.x},{self.y}), heading to waypoint {self.patrol_idx}")

    # ------------------------------------------------------------------ #
    #  Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    def _scan(self, game_map) -> None:
        """Add every visible walkable tile within SIGHT_RADIUS to cleared_tiles."""
        visible = _fov(game_map, self.x, self.y)
        xs, ys = np.where(visible & game_map.tiles["walkable"])
        for x, y in zip(xs.tolist(), ys.tolist()):
            self.cleared_tiles.add((x, y))

    def _try_share(self, other: "Enemy", game_map) -> None:
        """Merge cleared_tiles if the other enemy is in sight.
        If the other is still patrolling, recruit them into this search."""
        if _dist(self.x, self.y, other.x, other.y) > SIGHT_RADIUS:
            return
        if not _fov(game_map, self.x, self.y)[other.x, other.y]:
            return
        combined = self.cleared_tiles | other.cleared_tiles
        self.cleared_tiles = combined
        other.cleared_tiles = combined
        log.debug(f"E{self.eid} shared tiles with E{other.eid} — combined pool: {len(combined)}")
        if other.mode == Mode.PATROL:
            # Only recruit if there are at least 2 uncleared rooms to split.
            # Fewer than 2 means there's nothing useful for a second enemy to do,
            # and recruiting with 0 rooms caused an infinite re-recruit loop.
            uncleared = [r for r in self.search_rooms if not self._room_is_cleared(r, game_map)]
            if len(uncleared) <= 1:
                log.debug(f"E{self.eid} skipped recruiting E{other.eid} — only {len(uncleared)} rooms left")
                return

            # Split unchecked rooms so the two enemies cover different areas
            random.shuffle(uncleared)
            mid = len(uncleared) // 2
            self.search_rooms = uncleared[mid:]
            self.search_idx = 0
            self._path = []
            self._path_target = None

            log.info(
                f"E{self.eid} recruited E{other.eid} — split {len(uncleared)} rooms "
                f"({len(uncleared) - mid} / {mid})"
            )
            other._start_search_at(uncleared[:mid])
            other.cleared_tiles = combined  # restore after _start_search_at reset

    def _room_is_cleared(self, room, game_map) -> bool:
        """True when every walkable tile inside the room bounds is in cleared_tiles."""
        for x in range(room.x1 + 1, room.x2):
            for y in range(room.y1 + 1, room.y2):
                if game_map.tiles[x, y]["walkable"] and (x, y) not in self.cleared_tiles:
                    return False
        return True


# ------------------------------------------------------------------ #
#  Module-level helpers                                                #
# ------------------------------------------------------------------ #

def _fov(game_map, x: int, y: int, radius: int = SIGHT_RADIUS) -> np.ndarray:
    transparency = game_map.tiles["transparent"].astype(bool)
    fov = tcod.map.compute_fov(transparency, (x, y), radius=radius)
    if radius > 0:
        w, h = fov.shape
        dist_sq = (np.arange(w)[:, None] - x) ** 2 + (np.arange(h)[None, :] - y) ** 2
        fov &= dist_sq <= radius * radius
    return fov


def _dist(x1: int, y1: int, x2: int, y2: int) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def _compute_path(
    game_map, ox: int, oy: int, dx: int, dy: int,
    forbidden: set | None = None,
) -> List[Tuple[int, int]]:
    cost = np.array(game_map.tiles["walkable"], dtype=np.int8)
    if forbidden:
        for fx, fy in forbidden:
            if 0 <= fx < cost.shape[0] and 0 <= fy < cost.shape[1]:
                cost[fx, fy] = 0
    graph = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=3)
    pathfinder = tcod.path.Pathfinder(graph)
    pathfinder.add_root((ox, oy))
    raw = pathfinder.path_to((dx, dy))
    return [(int(p[0]), int(p[1])) for p in raw[1:]]
