"""Entry point: python main.py"""

from cadence import config, db, ingest
from cadence.tracker import Tracker

if __name__ == "__main__":
    token = config.load_or_create_token()
    ingest.serve_in_background(token)

    print(f"[cadence] tab ingest on http://{config.INGEST_HOST}:{config.INGEST_PORT}")
    print(f"[cadence] extension token: {token}")
    print(f"[cadence]   (also saved to {config.TOKEN_PATH})")

    Tracker(db.connect()).run()
