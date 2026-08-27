"""Runtime configuration. Everything lives under the user's local app data."""

import os
from pathlib import Path

APP_NAME = "Cadence"

DATA_DIR = Path(os.environ.get("CADENCE_DATA_DIR") or (Path.home() / ".cadence"))
DB_PATH = DATA_DIR / "cadence.db"

# How often the sampler wakes up. 1s is cheap (a few win32 calls) and gives
# us second-resolution activity density without any input hook.
POLL_SECONDS = 1.0

# No keyboard/mouse input for this long => the segment counts as idle.
IDLE_THRESHOLD_SECONDS = 60

# How often the open segment is written back to disk, so a crash or a
# hard shutdown loses at most this much of the current segment.
FLUSH_SECONDS = 15


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
