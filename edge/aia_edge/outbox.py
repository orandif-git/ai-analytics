"""SQLite outbox: events survive API outages and agent restarts, and are retried with the same client_id."""
import json
import sqlite3
import threading
import time


class Outbox:
    def __init__(self, path: str, max_rows: int = 100_000):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self.max_rows = max_rows
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, body TEXT)")
            self._db.commit()

    def put(self, event: dict) -> None:
        with self._lock:
            self._db.execute("INSERT INTO outbox (ts, body) VALUES (?, ?)", (time.time(), json.dumps(event)))
            # Bounded: during a long outage drop the OLDEST rows rather than fill the disk.
            self._db.execute(
                "DELETE FROM outbox WHERE id <= (SELECT max(id) FROM outbox) - ?", (self.max_rows,)
            )
            self._db.commit()

    def batch(self, n: int = 100) -> list[tuple[int, dict]]:
        with self._lock:
            rows = self._db.execute("SELECT id, body FROM outbox ORDER BY id LIMIT ?", (n,)).fetchall()
        return [(i, json.loads(b)) for i, b in rows]

    def delete(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._db.executemany("DELETE FROM outbox WHERE id = ?", [(i,) for i in ids])
            self._db.commit()

    def size(self) -> int:
        with self._lock:
            return self._db.execute("SELECT count(*) FROM outbox").fetchone()[0]
