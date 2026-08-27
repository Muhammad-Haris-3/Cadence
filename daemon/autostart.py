"""Start tracking automatically when Windows starts.

    python autostart.py status             # installed *and* actually running?
    python autostart.py start              # start it now, without a logon
    python autostart.py install            # Task Scheduler (preferred)
    python autostart.py install startup    # Startup folder (no elevation)
    python autostart.py uninstall          # removes both

`status` reports two separate things, because they failed independently once:
whether Windows is set to launch Cadence, and whether Cadence is running right
now. An installed shortcut that dies a second after logon looks identical to no
shortcut at all from the dashboard, and that is exactly what happened.

Two mechanisms, because they fail in different situations:

**Task Scheduler** is the better one. It can delay past the logon rush, it is
visible and removable from taskschd.msc, and it survives the interpreter moving.
But `schtasks /Create` is denied under some machine policies, and denial is not
predictable in advance.

**A Startup-folder shortcut** needs no special permission and works everywhere,
at the cost of firing during the logon rush with no delay control.

Both launch the venv's pythonw.exe, so no console window ever appears, and both
run unelevated -- tracking needs no privileges and should never ask for any.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

TASK_NAME = "Cadence Tracker"
SHORTCUT_NAME = "Cadence.lnk"

DAEMON_DIR = Path(__file__).resolve().parent
PYTHONW = DAEMON_DIR / ".venv" / "Scripts" / "pythonw.exe"
ENTRY = DAEMON_DIR / "tray_app.pyw"

# Past the logon rush, so tracking never competes with the desktop appearing.
LOGON_DELAY = "0000:30"


def startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def task_command() -> str:
    return f'"{PYTHONW}" "{ENTRY}"'


def preflight() -> list:
    problems = []
    if not PYTHONW.exists():
        problems.append(f"missing interpreter: {PYTHONW}")
    if not ENTRY.exists():
        problems.append(f"missing entry point: {ENTRY}")
    return problems


def _run(args) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


# -- Task Scheduler -----------------------------------------------------------


def install_task() -> int:
    result = _run([
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", task_command(),
        "/SC", "ONLOGON",
        "/DELAY", LOGON_DELAY,
        "/RL", "LIMITED",
        "/F",
    ])
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        print(f"Task Scheduler refused: {message}")
        if "denied" in message.lower():
            print(
                "\nThis machine's policy blocks creating scheduled tasks from a\n"
                "non-elevated shell. Either rerun this from an Administrator\n"
                "terminal, or use the mechanism that needs no elevation:\n\n"
                "    python autostart.py install startup"
            )
        return result.returncode

    delay = LOGON_DELAY.split(":")[1].lstrip("0") or "0"
    print(f"Installed scheduled task '{TASK_NAME}'.")
    print(f"Cadence will start {delay}s after you log in.")
    return 0


def uninstall_task(quiet: bool = False) -> bool:
    result = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if result.returncode == 0:
        print(f"Removed scheduled task '{TASK_NAME}'.")
        return True
    if not quiet:
        print(f"No scheduled task '{TASK_NAME}' to remove.")
    return False


def task_installed() -> bool:
    return _run(["schtasks", "/Query", "/TN", TASK_NAME]).returncode == 0


# -- Startup folder -----------------------------------------------------------


def install_startup() -> int:
    """Create the shortcut via WScript.Shell, so it points straight at
    pythonw.exe -- a .cmd file here would flash a console at every logon."""
    target = shortcut_path()
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath = '{exe}';"
        "$s.Arguments = '\"{entry}\"';"
        "$s.WorkingDirectory = '{cwd}';"
        "$s.Description = 'Cadence time tracker';"
        "$s.Save()"
    ).format(lnk=target, exe=PYTHONW, entry=ENTRY, cwd=DAEMON_DIR)

    result = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    if result.returncode != 0 or not target.exists():
        print((result.stderr or result.stdout).strip() or "could not create the shortcut")
        return 1

    print(f"Installed startup shortcut: {target}")
    print("Cadence will start when you log in.")
    return 0


def uninstall_startup(quiet: bool = False) -> bool:
    target = shortcut_path()
    if target.exists():
        target.unlink()
        print(f"Removed startup shortcut: {target}")
        return True
    if not quiet:
        print("No startup shortcut to remove.")
    return False


# -- commands -----------------------------------------------------------------


def running() -> bool:
    """Whether a Cadence is up right now, judged by the port it serves on."""
    sys.path.insert(0, str(DAEMON_DIR))
    from cadence import ingest

    return ingest.port_in_use()


def start() -> int:
    """Launch the tray app the same way the logon task does, and confirm it
    stayed up -- a start that reports success and then dies is the whole bug
    this command exists to catch."""
    if running():
        print("Cadence is already running.")
        return 0

    problems = preflight()
    if problems:
        for problem in problems:
            print(f"error: {problem}")
        return 1

    subprocess.Popen(
        [str(PYTHONW), str(ENTRY)],
        cwd=str(DAEMON_DIR),
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )

    for _ in range(20):
        time.sleep(0.5)
        if running():
            print("Cadence is running. Dashboard: http://127.0.0.1:8765/")
            return 0

    print("Cadence did not come up within 10s.")
    print(f"The reason will be in the log: {log_path()}")
    return 1


def log_path() -> Path:
    sys.path.insert(0, str(DAEMON_DIR))
    from cadence import logs

    return logs.LOG_PATH


def status() -> int:
    problems = preflight()
    for problem in problems:
        print(f"warning: {problem}")

    task = task_installed()
    shortcut = shortcut_path().exists()
    live = running()

    print(f"Scheduled task      {'installed' if task else 'not installed'}")
    print(f"Startup shortcut    {'installed' if shortcut else 'not installed'}")
    print(f"Running now         {'yes' if live else 'no'}")
    print(f"Log                 {log_path()}")
    print(f"\nWould run: {task_command()}")

    if task and shortcut:
        print(
            "\nBoth are installed. Only one is needed -- the second instance will\n"
            "refuse to start rather than double-count, but remove one anyway."
        )
    elif not task and not shortcut:
        print("\nNot starting automatically. Install with:  python autostart.py install")

    if (task or shortcut) and not live:
        print(
            "\nSet to start automatically, but not running. Either you haven't\n"
            "logged in since installing it, or it started and died -- the log\n"
            "above says which. Start it now with:  python autostart.py start"
        )
    return 0


def install(method: str = "task") -> int:
    problems = preflight()
    if problems:
        for problem in problems:
            print(f"error: {problem}")
        return 1

    if method == "startup":
        return install_startup()
    return install_task()


def uninstall() -> int:
    removed = uninstall_task(quiet=True) | uninstall_startup(quiet=True)
    if not removed:
        print("Nothing to remove; Cadence was not set to start automatically.")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    argument = sys.argv[2] if len(sys.argv) > 2 else "task"

    if command == "status":
        raise SystemExit(status())
    if command == "start":
        raise SystemExit(start())
    if command == "install":
        raise SystemExit(install(argument))
    if command == "uninstall":
        raise SystemExit(uninstall())

    print("usage: python autostart.py [status | start | install [startup] | uninstall]")
    raise SystemExit(2)
