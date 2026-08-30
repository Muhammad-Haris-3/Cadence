"""Start tracking automatically when Windows starts.

    python autostart.py status             # installed, enabled *and* running?
    python autostart.py start              # start it now
    python autostart.py install            # Task Scheduler (preferred)
    python autostart.py install startup    # Startup folder (last resort)
    python autostart.py uninstall          # removes both

`status` reports three separate things, because they failed independently once:
whether Windows is set to launch Cadence, whether it is running right now, and
-- the one that took three rounds of "it lost everything" to find -- *how long
after logon* it actually started.

That last number is the whole reason this file prefers Task Scheduler.

The Startup folder looks like it works: the shortcut is there, and Cadence does
come up after every logon. But the shell runs Startup-folder items whenever it
gets round to them, behind every other startup app, throttled by Windows' own
startup-app policy. Measured on a real machine across four consecutive logons,
that was 5:00, 5:28, 5:39 and 6:27 -- every time, minutes of a dashboard saying
the tracker isn't running while the tracker is simply not launched yet. There
is no setting to make that shorter, because the delay is not ours.

A scheduled task has a trigger with a delay we name, honoured by the Task
Scheduler service rather than the shell, and it takes a second trigger: a
repetition that relaunches Cadence if it is ever not running, which turns
"start it again" into something nobody has to remember.

Four of its settings matter more than the rest, and all four default the wrong
way for a laptop:

    DisallowStartIfOnBatteries   true by default -- the task would simply not
                                 run while unplugged, which is most of the time
    StopIfGoingOnBatteries       true by default -- unplugging would kill it
    ExecutionTimeLimit           72 hours by default -- a process meant to run
                                 for months gets terminated after three days
    MultipleInstancesPolicy      the repetition must not start a second copy

`schtasks /Create` with plain flags cannot set any of them, which is why the
task is registered from XML.

Both mechanisms launch the venv's pythonw.exe, so no console window ever
appears, and both run unelevated -- tracking needs no privileges and should
never ask for any.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TASK_NAME = "Cadence Tracker"
SHORTCUT_NAME = "Cadence.lnk"

DAEMON_DIR = Path(__file__).resolve().parent
PYTHONW = DAEMON_DIR / ".venv" / "Scripts" / "pythonw.exe"
ENTRY = DAEMON_DIR / "tray_app.pyw"

# Long enough to be behind the logon itself, short enough that opening the
# dashboard straight after logging in finds a tracker already answering.
LOGON_DELAY = "PT20S"

# The watchdog, and the worst-case hole an unexplained death leaves in the day:
# whatever happens, tracking resumes within one tick. Every tick launches the
# tray app, which checks the port before importing anything heavy and exits in
# milliseconds when Cadence is already up -- cheap enough that the interval is
# chosen for how much time may be lost, not for what the check costs.
WATCHDOG_INTERVAL = "PT2M"


def startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def task_command() -> str:
    return f'"{PYTHONW}" "{ENTRY}"'


def account() -> str:
    """The user the task runs as. Tracking reads the foreground window, so it
    has to be this session -- never SYSTEM, which has no desktop to look at."""
    domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or ""
    user = os.environ.get("USERNAME", "")
    return "\\".join(part for part in (domain, user) if part)


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


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# -- Task Scheduler -----------------------------------------------------------


def task_xml() -> str:
    """The task definition. Every non-obvious setting is here on purpose --
    see the module docstring for the four that default the wrong way."""
    who = _xml_escape(account())
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Cadence time tracker. Starts at logon and is restarted if it stops.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{who}</UserId>
      <Delay>{LOGON_DELAY}</Delay>
    </LogonTrigger>
    <TimeTrigger>
      <Enabled>true</Enabled>
      <StartBoundary>2020-01-01T00:00:00</StartBoundary>
      <Repetition>
        <Interval>{WATCHDOG_INTERVAL}</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{who}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml_escape(str(PYTHONW))}</Command>
      <Arguments>"{_xml_escape(str(ENTRY))}"</Arguments>
      <WorkingDirectory>{_xml_escape(str(DAEMON_DIR))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def install_task() -> int:
    # schtasks reads the definition as UTF-16; anything else is rejected with a
    # parse error that does not mention encoding.
    handle, path = tempfile.mkstemp(suffix=".xml", prefix="cadence-task-")
    os.close(handle)
    Path(path).write_text(task_xml(), encoding="utf-16")

    try:
        result = _run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", path, "/F"])
    finally:
        os.unlink(path)

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        print(f"Task Scheduler refused: {message}")
        if "denied" in message.lower():
            print(
                "\nThis machine's policy blocks creating scheduled tasks from a\n"
                "non-elevated shell. Either rerun this from an Administrator\n"
                "terminal, or fall back to the mechanism that needs no elevation:\n\n"
                "    python autostart.py install startup\n\n"
                "Be aware that the Startup folder is what made Cadence appear\n"
                "five minutes late after every logon."
            )
        return result.returncode

    seconds = LOGON_DELAY.removeprefix("PT").removesuffix("S")
    minutes = WATCHDOG_INTERVAL.removeprefix("PT").removesuffix("M")
    print(f"Installed scheduled task '{TASK_NAME}'.")
    print(f"  starts    {seconds}s after you log in")
    print(f"  recovers  checked every {minutes} minutes; restarted if it isn't running")

    # One mechanism, not two. The shortcut is the slow one, and leaving it in
    # place would keep launching a second copy five minutes into every session
    # -- harmless, because it refuses the port, but it would put a "not starting
    # a second instance" warning in the log at every logon for no reason.
    if shortcut_path().exists():
        shortcut_path().unlink()
        print(f"  removed   the old Startup shortcut ({shortcut_path().name})")
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


def task_details() -> dict:
    """What Task Scheduler thinks of the task: enabled, last run, last result.

    An installed-but-disabled task reads exactly like a working one from a
    dashboard, which is the failure this whole file exists to stop repeating.
    """
    result = _run(["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"])
    if result.returncode != 0:
        return {}

    wanted = {
        "Scheduled Task State": "state",
        "Last Run Time": "last_run",
        "Last Result": "last_result",
        "Next Run Time": "next_run",
    }
    found = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(":")
        name = wanted.get(key.strip())
        if name and name not in found:
            found[name] = value.strip()
    return found


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
    print("Cadence will start when you log in -- but on a measured machine that")
    print("was five to six minutes after logon, every time. Prefer the task:")
    print("    python autostart.py install")
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
    details = task_details() if task else {}
    shortcut = shortcut_path().exists()
    live = running()

    state = details.get("state", "")
    print(f"Scheduled task      {state.lower() if state else 'not installed'}")
    if details:
        print(f"  last run          {details.get('last_run', '?')}"
              f"  (result {details.get('last_result', '?')})")
        print(f"  next run          {details.get('next_run', '?')}")
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
    elif shortcut and not task:
        print(
            "\nRunning on the Startup folder, which launches Cadence whenever the\n"
            "shell gets round to it -- measured at five to six minutes after every\n"
            "logon. The scheduled task starts it in seconds and restarts it if it\n"
            "ever stops:  python autostart.py install"
        )

    if (task or shortcut) and not live:
        print(
            "\nSet to start automatically, but not running right now. Nothing that\n"
            "was already recorded is affected -- the database is only ever appended\n"
            "to. Start it now with:  python autostart.py start"
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
