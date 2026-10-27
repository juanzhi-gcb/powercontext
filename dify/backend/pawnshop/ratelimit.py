"""Per-player fixed-window limiter stored in SQLite so every worker agrees."""
import time

from fastapi import HTTPException


class RateLimiter:
    def __init__(self, store, limit, window_seconds=60):
        self.store, self.limit, self.window_seconds = store, limit, window_seconds

    def check(self, key):
        if self.limit <= 0:
            return
        window = int(time.time()) // self.window_seconds
        with self.store.connect(write=True) as conn:
            row = conn.execute("SELECT window_start,count FROM rate_limits WHERE key=?", (key,)).fetchone()
            if row is None or row["window_start"] != window:
                conn.execute("INSERT INTO rate_limits(key,window_start,count) VALUES(?,?,1) "
                             "ON CONFLICT(key) DO UPDATE SET window_start=excluded.window_start,count=1",
                             (key, window))
                count = 1
            else:
                count = row["count"] + 1
                conn.execute("UPDATE rate_limits SET count=? WHERE key=?", (count, key))
        if count > self.limit:
            raise HTTPException(429, "请求过于频繁，请稍后再试")