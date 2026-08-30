"""The no-console contract: Cadence must start under pythonw.exe.

This is the regression that made autostart look like it had never been
installed. Launched at logon through pythonw, `sys.stdout` and `sys.stderr` are
None -- not closed files, None. Uvicorn's default log config asks
`sys.stdout.isatty()` to decide about colour, so building a `uvicorn.Config`
raised before the tray icon or the sampler existed. The process was gone within
a second, with no console, no window and no log: the only visible symptom was a
dashboard saying the tracker wasn't running.

So the checks here run with the std streams set to None, which is the only way
to reproduce it -- under a normal test run the streams exist and everything
passes whether or not the bug is present.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CADENCE_DATA_DIR"] = tempfile.mkdtemp(prefix="cadence-test-")


class no_console:
    """What pythonw.exe hands a process."""

    def __enter__(self):
        self._saved = (sys.stdout, sys.stderr)
        sys.stdout = sys.stderr = None
        return self

    def __exit__(self, *_):
        sys.stdout, sys.stderr = self._saved
        return False


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  ' + detail if detail and not ok else ''}")
    return bool(ok)


def main() -> int:
    from cadence import ingest, logs

    results = []

    # 1. The server config as ingest actually builds it -- the exact call that
    #    used to raise. No port is bound, so this is safe while Cadence runs.
    with no_console():
        try:
            ingest.server_config("token")
            raised = None
        except Exception as exc:  # noqa: BLE001 -- the failure is the result
            raised = exc
    results.append(check("ingest's server config builds with no stdout", raised is None,
                         repr(raised)))

    # 2. Logging must work without a console, and must give the process usable
    #    std streams back, so a library that assumes one finds one.
    with no_console():
        try:
            log = logs.setup()
            log.info("hello from a console-less process")
            bound = sys.stdout is not None and sys.stderr is not None
            isatty = sys.stdout.isatty()
            failed = None
        except Exception as exc:  # noqa: BLE001
            bound, isatty, failed = False, None, exc
    results.append(check("logs.setup() survives no stdout", failed is None, repr(failed)))
    results.append(check("std streams rebound to the log file", bound))
    results.append(check("rebound stdout answers isatty()", isatty is False))

    # 3. And the log actually has the line in it -- a handler that silently
    #    drops records would pass everything above.
    written = logs.LOG_PATH.exists() and "hello from a console-less process" in \
        logs.LOG_PATH.read_text(encoding="utf-8")
    results.append(check("the line reached the log file", written))

    # 4. The watchdog runs the entry point every couple of minutes and almost
    #    always finds Cadence already up. That path must not drag in the web
    #    stack: reaching the port check through `ingest` imported fastapi,
    #    uvicorn, pydantic and pystray -- 0.7s of a warm machine, far more of a
    #    cold one -- to learn what a socket bind answers in a third of a
    #    millisecond, a few hundred times a day, on a laptop.
    snippet = (
        "import sys; sys.path.insert(0, %r);"
        "from cadence import config; config.port_in_use();"
        "print(','.join(m for m in ('fastapi','uvicorn','pydantic','pystray','PIL')"
        "               if m in sys.modules))" % str(ROOT)
    )
    probe = subprocess.run([sys.executable, "-c", snippet],
                           capture_output=True, text=True)
    results.append(check("the port check pulls in nothing heavy",
                         probe.stdout.strip() == "",
                         probe.stdout.strip() or probe.stderr.strip()))

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
