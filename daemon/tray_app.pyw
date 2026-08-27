"""Console-free entry point for the tray app.

The .pyw extension keeps Windows from opening a console window. This is what the
logon task launches, via the venv's pythonw.exe.
"""

import sys

from cadence.tray import run

if __name__ == "__main__":
    sys.exit(run())
