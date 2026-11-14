# bandcamp-scout

Takes your track list, finds each track on Bandcamp, and reports whether it's free, name-your-price (NYP) or paid. It only reports: it doesn't buy, download or touch Spotify.

Bandcamp has no public catalog API, so this uses undocumented endpoints confirmed in [docs/findings.md](docs/findings.md). It's polite about it: one request at a time, ~1/s with jitter, backoff on 429/5xx, and everything is cached in SQLite (30-day TTL).

## Install

```
uv sync                # add --extra gui for the settings window
uv run scout --help    # or: uv tool install . && scout --help
```

## Input

By default tracks come from the [Spotify Subgenre Assistant](https://github.com/druppin/Spotify-subgenre-helper)'s library API (`127.0.0.1:3000`, only while the app runs). Create a key with `npm run api-token create "bandcamp-scout"`, then set it in `scout gui` or in `~/.config/bandcamp-scout/config.toml`:

```toml
[sgh]
url = "http://127.0.0.1:3000/api/v1"
api_key = "sgh_…"

[input]
playlists = ["liked"]      # or "all"
mixxx_db = ""              # optional read-only mixxxdb.sqlite copy; adds tracks not in any playlist

[schedule]
mode = "manual"            # or "weekly" (installs a systemd user timer)
weekday = "Mon"
time = "09:00"
```

`SGH_URL` / `SGH_API_KEY` env vars override the file. With no config file, `scout run` scans Liked Songs only and warns. Or skip the Assistant: `--csv tracks.csv` with columns `artist,title[,duration_s,isrc,spotify_id]` (several artists as `A; B`).

## Use

```
scout inputs --playlist liked              # what would be scouted
scout lookup "Calibre" "Even If" --duration 454
scout run --limit 25                       # resumable; Ctrl-C and re-run
scout report --out report.csv [--only free,nyp_zero,nyp_min,review]
scout override KEY --url URL | --none      # manual fix, always wins, survives --refresh
scout stats
scout gui                                  # settings window
```

The cache lives at `~/.local/share/bandcamp-scout/scout.db` (`--db` to move it, e.g. into a Syncthing folder for the mixxx-harness mod).

## Matching

Artist and title are normalized (accents, `&`, feat., `(Original Mix)`, `[Label]`), the remix/edit name is kept separate, and each candidate gets a 0–1 score: title 0.45, artist 0.35, duration 0.20 (full within ±3 s, zero at ±15 s, 0.5 if unknown). A version mismatch (remix vs original, different remixers) caps the score at 0.5. ≥ 0.90 is `match`, 0.75–0.90 `review`, below that `no_match`. Bootleg uploads titled "Artist - Title" on someone else's account are handled; a wrong-length reupload lands in `review`, never `match`.

Price types: `free`, `nyp_zero`, `nyp_min`, `paid`, `album_only` (track not sold alone; album price shown), `not_for_sale`, `unknown` (a field was missing; never guessed). The album's own price type is reported next to the track's.

## Tests

```
uv run python -m unittest discover tests
```

Offline only: saved search responses and pages in `tests/fixtures/`.

## Results

Go/no-go numbers for the mixxx-harness mod (Phase 5) go here after the first full run (`scout stats`).
