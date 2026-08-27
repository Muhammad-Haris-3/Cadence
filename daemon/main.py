"""Entry point: python main.py"""

from cadence import db
from cadence.tracker import Tracker

if __name__ == "__main__":
    Tracker(db.connect()).run()
