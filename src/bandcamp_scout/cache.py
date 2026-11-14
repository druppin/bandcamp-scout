"""scout.db: one SQLite file holding inputs, raw searches, parsed pages, results and overrides."""
import json
import sqlite3
from datetime import UTC, datetime, timedelta

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS inputs (key TEXT PRIMARY KEY, artists TEXT NOT NULL, title TEXT NOT NULL,
    duration_s REAL, isrc TEXT, spotify_id TEXT);
CREATE TABLE IF NOT EXISTS searches (query TEXT PRIMARY KEY, response TEXT NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, candidate TEXT NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, track_url TEXT, album_url TEXT,
    status TEXT NOT NULL, score REAL, price_type TEXT, price REAL, currency TEXT,
    album_price_type TEXT, album_price REAL, checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS overrides (key TEXT PRIMARY KEY, url TEXT);  -- url NULL = not on Bandcamp
"""
RESULT_COLS = ("track_url", "album_url", "status", "score", "price_type", "price", "currency",
               "album_price_type", "album_price")


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def is_fresh(stamp: str | None, ttl_days: float) -> bool:
    return bool(stamp) and datetime.fromisoformat(stamp) > datetime.now(UTC) - timedelta(days=ttl_days)


class Cache:
    def __init__(self, path):
        self.con = sqlite3.connect(path)
        self.con.executescript(SCHEMA)
        row = self.con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None:
            self.con.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            self.con.commit()
        elif int(row[0]) != SCHEMA_VERSION:
            raise RuntimeError(f"{path}: schema_version {row[0]}, this scout expects {SCHEMA_VERSION}")

    def close(self):
        self.con.close()

    # inputs
    def put_inputs(self, tracks):
        self.con.executemany("INSERT OR REPLACE INTO inputs VALUES (?,?,?,?,?,?)",
                             [(t.key, json.dumps(t.artists), t.title, t.duration_s, t.isrc, t.spotify_id)
                              for t in tracks])
        self.con.commit()

    def get_input(self, key):
        from .inputs import InputTrack
        row = self.con.execute("SELECT * FROM inputs WHERE key=?", (key,)).fetchone()
        return row and InputTrack(row[0], tuple(json.loads(row[1])), *row[2:])

    # raw fetches
    def get_search(self, query, ttl_days):
        row = self.con.execute("SELECT response, fetched_at FROM searches WHERE query=?", (query,)).fetchone()
        return json.loads(row[0]) if row and is_fresh(row[1], ttl_days) else None

    def put_search(self, query, response):
        self.con.execute("INSERT OR REPLACE INTO searches VALUES (?,?,?)", (query, json.dumps(response), now()))
        self.con.commit()

    def get_page(self, url, ttl_days):
        row = self.con.execute("SELECT candidate, fetched_at FROM pages WHERE url=?", (url,)).fetchone()
        return row[0] if row and is_fresh(row[1], ttl_days) else None

    def put_page(self, url, candidate_json):
        self.con.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?)", (url, candidate_json, now()))
        self.con.commit()

    # results
    def result_checked_at(self, key):
        row = self.con.execute("SELECT checked_at FROM results WHERE key=?", (key,)).fetchone()
        return row and row[0]

    def put_result(self, key, result: dict):
        self.con.execute(f"INSERT OR REPLACE INTO results (key, {', '.join(RESULT_COLS)}, checked_at) "
                         f"VALUES (?, {', '.join('?' * len(RESULT_COLS))}, ?)",
                         (key, *(result.get(c) for c in RESULT_COLS), now()))
        self.con.commit()

    def rows(self):
        """Joined inputs+results, for the report. Overrides already applied by the run."""
        cur = self.con.execute(
            "SELECT i.key, i.artists, i.title, r.*, o.key IS NOT NULL FROM inputs i "
            "JOIN results r ON r.key = i.key LEFT JOIN overrides o ON o.key = i.key")
        names = [d[0] for d in cur.description]
        out = []
        for row in cur:
            d = dict(zip(names[:3], row[:3]))
            d.update(zip(names[3:-1], row[3:-1]))
            d["artists"] = json.loads(d["artists"])
            d["overridden"] = bool(row[-1])
            out.append(d)
        return out

    # overrides
    def set_override(self, key, url):
        self.con.execute("INSERT OR REPLACE INTO overrides VALUES (?,?)", (key, url))
        self.con.commit()

    def get_override(self, key):
        """None = no override; (url,) where url None means 'not on Bandcamp'."""
        row = self.con.execute("SELECT url FROM overrides WHERE key=?", (key,)).fetchone()
        return row and (row[0],)
