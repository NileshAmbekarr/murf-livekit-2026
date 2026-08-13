import sqlite3
import time
from pathlib import Path
import os
import logging

logger = logging.getLogger("sehat-sathi.analytics")

ANALYTICS_DB_PATH = os.getenv("ANALYTICS_DB_PATH", "data/analytics.db")

class AnalyticsStore:
    """Stores basic call outcomes for the dashboard."""

    def __init__(self, db_path: str = ANALYTICS_DB_PATH):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            # We use WAL mode to allow concurrent reads from the Next.js dashboard
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS calls (
                    room_name TEXT PRIMARY KEY,
                    timestamp INTEGER NOT NULL,
                    successful BOOLEAN NOT NULL,
                    reason TEXT
                )
                '''
            )
            conn.commit()

    def record_call(self, room_name: str, successful: bool, reason: str = "") -> None:
        """Record the outcome of a call."""
        if not room_name:
            return
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT OR REPLACE INTO calls (room_name, timestamp, successful, reason)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (room_name, int(time.time()), successful, reason)
                )
                conn.commit()
            logger.info("recorded call outcome", extra={"room_name": room_name, "successful": successful, "reason": reason})
        except Exception as e:
            logger.error("failed to record call outcome", extra={"error": str(e)})

analytics_store = AnalyticsStore()
