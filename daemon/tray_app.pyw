"""Console-free entry point for the tray app.

The .pyw extension keeps Windows from opening a console window. This is what the
logon task launches, via the venv's pythonw.exe.

Under pythonw there is no stdout and no stderr -- they are None, not closed
files -- so the log file is opened before anything else is imported. A library
that touches sys.stdout at import time would otherwise take the whole process
down with nothing written anywhere.

Nothing expensive is imported until it is known to be needed. A watchdog runs
this file every couple of minutes and almost always finds Cadence already up,
so the common path through here has to be a socket bind and an exit.
"""

import sys
import traceback
from pathlib import Path

# Launched by a shortcut, the working directory is whatever the shortcut says;
# don't depend on it for the package import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cadence import logs  # noqa: E402  -- must precede every other import

logs.setup()

# Asked before anything heavy is imported, because most of the times this file
# runs it is the watchdog checking, the answer is "already running", and the
# right thing to do is nothing at all. Importing the tray app first to find that
# out cost 0.7s of a warm machine and considerably more of a cold one, a few
# hundred times a day, on a laptop. The check itself is a socket bind.
from cadence import config  # noqa: E402

if config.port_in_use():
    logs.get().debug("port %s already in use; nothing to do", config.INGEST_PORT)
    raise SystemExit(0)

try:
    from cadence.tray import run
except Exception:
    logs.get().error("Cadence could not be imported:\n%s", traceback.format_exc())
    raise

if __name__ == "__main__":
    sys.exit(run())
