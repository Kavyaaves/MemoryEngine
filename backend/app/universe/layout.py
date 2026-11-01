"""Where each Memory Book floats in 3D. Pure math: no database, no randomness.

The universe is built around a "time river" — a straight line along the x axis:

    x      = days since 1 Jan 2000 × UNITS_PER_DAY      (chronological time)
    angle  = a fixed angle for the book's *lane*          (who / which conversation it is about)
    radius = how far from the river                       (grows only to avoid overlapping a book)

    y = radius · sin(angle),  z = radius · cos(angle)

So books with the same person stay on the same side of the river year after year, and a year
is always the same stretch of river.

Stability rules (PLAN: "existing objects keep their positions"):
- A book's position is computed once, when the book is created, and stored. It is never
  recomputed, even if the book later grows to cover more days.
- The origin is a fixed date, not "your oldest memory" — so uploading older memories later
  adds books further left without moving anything that already exists.
- The lane angle comes from a SHA-256 hash (Python's built-in hash() changes between runs).
- A new book that would overlap an existing one moves itself; existing books never move.
"""

import hashlib
import math
from datetime import date, datetime

from app.core.timeutils import make_aware, user_timezone

ORIGIN = date(2000, 1, 1)
UNITS_PER_DAY = 0.4  # one year ≈ 146 units of river
RIVER_RADIUS = 7.0  # the first ring of books around the river
RING_STEP = 2.6  # each further ring is this much further out
MIN_SPACING = 2.4  # two books closer than this would overlap (a book is about 1.2 units tall)
ANGLE_STEP = math.radians(22)  # tried on alternate sides of the lane before moving out a ring
ANGLE_TRIES = 7  # the lane angle, then ±1, ±2, ±3 steps
MAX_RINGS = 6

Position = tuple[float, float, float]


def local_date(moment: datetime) -> date:
    """The calendar day of `moment` in the user's timezone (a message at 00:30 IST is that day)."""
    return make_aware(moment).astimezone(user_timezone()).date()


def time_x(moment: datetime | date) -> float:
    """Position along the time river. Whole days only, so the same day always gives the same x."""
    day = moment if not isinstance(moment, datetime) else local_date(moment)
    return (day - ORIGIN).days * UNITS_PER_DAY


def lane_angle(lane_key: str) -> float:
    """A fixed angle (radians, 0..2π) for a lane such as a person id or a conversation id."""
    digest = hashlib.sha256(lane_key.encode("utf-8")).digest()
    return (int.from_bytes(digest[:4], "big") % 3600) / 3600 * 2 * math.pi


def _distance(a: Position, b: Position) -> float:
    return math.dist(a, b)


def place_book(start_at: datetime, lane_key: str, existing: list[Position]) -> Position:
    """The position for a NEW book. `existing` are the positions of books already placed
    (only the ones near this x matter; far ones are ignored)."""
    x = time_x(start_at)
    nearby = [p for p in existing if abs(p[0] - x) < MIN_SPACING]
    base_angle = lane_angle(lane_key)

    candidate: Position = (x, 0.0, RIVER_RADIUS)
    for ring in range(MAX_RINGS):
        radius = RIVER_RADIUS + ring * RING_STEP
        for attempt in range(ANGLE_TRIES):
            # attempt 0 → lane angle; 1 → one step one way; 2 → one step the other way; 3 → two steps …
            steps = (attempt + 1) // 2
            direction = 1 if attempt % 2 == 1 else -1
            angle = base_angle + direction * steps * ANGLE_STEP
            candidate = (x, round(radius * math.sin(angle), 4), round(radius * math.cos(angle), 4))
            if all(_distance(candidate, other) >= MIN_SPACING for other in nearby):
                return candidate
    return candidate  # extremely crowded day: accept a small overlap rather than fly off into space
