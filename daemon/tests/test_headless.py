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
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
