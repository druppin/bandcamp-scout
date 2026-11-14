"""Load tracks to scout: the Subgenre Assistant's library API, a CSV, or a Mixxx library copy."""
import csv
import hashlib
import sqlite3
from dataclasses import dataclass

import httpx

from .match import normalize


class InputError(Exception):
    pass


@dataclass(frozen=True)
class InputTrack:
    key: str  # Spotify track id, else ISRC, else hash(artist, title)
    artists: tuple[str, ...]
    title: str
    duration_s: float | None
    isrc: str | None
    spotify_id: str | None


def name_key(artists, title) -> str:
    return "h:" + hashlib.sha1(f"{normalize(' '.join(artists))}|{normalize(title)}".encode()).hexdigest()[:16]


def make_track(artists, title, duration_s=None, isrc=None, spotify_id=None) -> InputTrack:
    artists = tuple(a for a in artists if a)
    key = spotify_id or (f"isrc:{isrc}" if isrc else name_key(artists, title))
    return InputTrack(key, artists, title, duration_s, isrc or None, spotify_id or None)


def _dedupe(tracks):
    seen, out = set(), []
    for t in tracks:
        if t.key not in seen:
            seen.add(t.key)
            out.append(t)
    return out


def from_song(song: dict) -> InputTrack:
    ms = song.get("durationMs")
    return make_track(song.get("artists") or [], song.get("title") or "", ms / 1000 if ms else None,
                      song.get("isrc"), song.get("id"))


def _sgh_getter(base_url: str, api_key: str, transport=None):
    """Returns get(path) -> JSON, turning connection/auth failures into readable InputErrors."""
    if not api_key:
        raise InputError("No Subgenre Assistant API key. Set SGH_API_KEY or sgh.api_key in config.toml "
                         "(create one with: npm run api-token create \"bandcamp-scout\").")
    http = httpx.Client(base_url=base_url.rstrip("/") + "/", timeout=30, transport=transport,
                        headers={"Authorization": f"Bearer {api_key.strip()}"})

    def get(path):
        try:
            r = http.get(path)
        except httpx.ConnectError:
            raise InputError(f"Can't reach the Subgenre Assistant at {base_url}. Is the app running?") from None
        if r.status_code == 401:
            raise InputError("The Subgenre Assistant rejected the API key (401). Check sgh.api_key.")
        if r.status_code == 404:
            raise InputError(f"Not found on the Subgenre Assistant: {r.url} (check the URL ends in /api/v1)")
        r.raise_for_status()
        return r.json()
    return get


def load_sgh(base_url: str, api_key: str, playlists="all", transport=None) -> list[InputTrack]:
    """playlists: "all" (every playlist plus liked) or a list of ids."""
    get = _sgh_getter(base_url, api_key, transport)
    if playlists == "all":
        ids = [p["id"] for p in get("playlists")["playlists"]]
        playlists = ["liked"] + [i for i in ids if i != "liked"]
    tracks = [from_song(s) for pid in playlists for s in get(f"playlists/{pid}/tracks")["tracks"]]
    return _dedupe(tracks)


def list_playlists(base_url: str, api_key: str, transport=None) -> list[dict]:
    return _sgh_getter(base_url, api_key, transport)("playlists")["playlists"]


def load_csv(path) -> list[InputTrack]:
    """Columns: artist, title, and optionally duration_s, isrc, spotify_id. Several artists: 'A; B'."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if rows and not {"artist", "title"} <= rows[0].keys():
        raise InputError(f"{path}: needs 'artist' and 'title' columns")
    return _dedupe(make_track([a.strip() for a in (r["artist"] or "").split(";")], r["title"] or "",
                              float(r["duration_s"]) if r.get("duration_s") else None,
                              r.get("isrc"), r.get("spotify_id")) for r in rows if r.get("title"))


def load_mixxx(path) -> list[InputTrack]:
    """Read-only. Mixxx's `library.duration` is in seconds."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        # only rows with a file on disk: library also holds non-DJ entries (cratesync findings)
        rows = con.execute("SELECT l.artist, l.title, l.duration FROM library l "
                           "JOIN track_locations t ON t.id = l.location "
                           "WHERE l.mixxx_deleted = 0 AND t.fs_deleted = 0 AND l.title != ''").fetchall()
    finally:
        con.close()
    return _dedupe(make_track([artist or ""], title, duration or None) for artist, title, duration in rows)


def merge(primary: list[InputTrack], extra: list[InputTrack]) -> list[InputTrack]:
    """Add `extra` tracks whose artist+title isn't already in `primary`."""
    known = {name_key(t.artists, t.title) for t in primary}
    return primary + [t for t in extra if name_key(t.artists, t.title) not in known]
