"""Time utilities shared across graph nodes."""

from __future__ import annotations

import time


def now_ms() -> int:
    """Return the current Unix timestamp in milliseconds.

    Returns:
        Current time as an integer number of milliseconds since the epoch.
    """
    return int(time.time() * 1000)
