"""Entry point: python main.py"""

from cadence import config, db, ingest, web
from cadence.tracker import Tracker

if __name__ == "__main__":
    token = config.load_or_create_token()
    ingest.serve_in_background(token, web.build_app(token))

    base = f"http://{config.INGEST_HOST}:{config.INGEST_PORT}"
    print(f"[cadence] dashboard      {base}/")
    print(f"[cadence] tab ingest     {base}/tab")
    print(f"[cadence] extension token: {token}")
    print(f"[cadence]   (also saved to {config.TOKEN_PATH})")

    Tracker(db.connect()).run()
