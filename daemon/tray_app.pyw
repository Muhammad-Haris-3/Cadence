"""Console-free entry point for the tray app.

The .pyw extension keeps Windows from opening a console window. This is what the
logon task launches, via the venv's pythonw.exe.

Under pythonw there is no stdout and no stderr -- they are None, not closed
files -- so the log file is opened before anything else is imported. A library
that touches sys.stdout at import time would otherwise take the whole process
down with nothing written anywhere.
"""

import sys
import traceback
from pathlib import Path

# Launched by a shortcut, the working directory is whatever the shortcut says;
# don't depend on it for the package import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cadence import logs  # noqa: E402  -- must precede every other import

logs.setup()

try:
    from cadence.tray import run
except Exception:
    logs.get().error("Cadence could not be imported:\n%s", traceback.format_exc())
    raise

if __name__ == "__main__":
    sys.exit(run())
