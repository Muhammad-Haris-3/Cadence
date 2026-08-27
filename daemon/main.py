"""Entry point: python main.py

Runs the sampler in the foreground with a console. For everyday use prefer the
tray app, which needs no terminal left open:  pythonw tray_app.pyw
"""

import sys

from cadence import config, db, ingest, logs, web
from cadence.tracker import Tracker

ALREADY_RUNNING = """[cadence] port {port} is already in use -- Cadence is probably
          running already (check the tray). Two samplers on one
          database would count every second twice."""

if __name__ == "__main__":
    logs.setup(console=True)

    if ingest.port_in_use():
        print(ALREADY_RUNNING.format(port=config.INGEST_PORT))
        sys.exit(1)

    token = config.load_or_create_token()
    ingest.serve_in_background(token, web.build_app(token))

    base = f"http://{config.INGEST_HOST}:{config.INGEST_PORT}"
    print(f"[cadence] dashboard      {base}/")
    print(f"[cadence] tab ingest     {base}/tab")
    print(f"[cadence] extension token: {token}")
    print(f"[cadence]   (also saved to {config.TOKEN_PATH})")

    Tracker(db.connect()).run()
