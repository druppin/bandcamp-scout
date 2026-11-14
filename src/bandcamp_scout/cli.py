import argparse
import sys

import httpx
from pathlib import Path

from . import config, inputs, pricing, report, scout
from .cache import Cache, is_fresh
from .http import Client

DEFAULT_DB = Path.home() / ".local" / "share" / "bandcamp-scout" / "scout.db"


def load_tracks(args) -> list[inputs.InputTrack]:
    if getattr(args, "csv", None):
        return inputs.load_csv(args.csv)
    cfg, existed = config.load()
    playlists = args.playlist or cfg["input"]["playlists"]
    if not existed and not args.playlist:
        print(f"warning: no {config.CONFIG_PATH}; scanning Liked Songs only (run `scout gui` to choose)",
              file=sys.stderr)
    tracks = inputs.load_sgh(cfg["sgh"]["url"], cfg["sgh"]["api_key"], playlists)
    if cfg["input"].get("mixxx_db") and not args.playlist:
        tracks = inputs.merge(tracks, inputs.load_mixxx(cfg["input"]["mixxx_db"]))
    return tracks


def cmd_inputs(args):
    tracks = load_tracks(args)
    for t in tracks:
        dur = f"{t.duration_s:.0f}s" if t.duration_s else "?"
        print(f"{t.key}\t{', '.join(t.artists)}\t{t.title}\t{dur}")
    print(f"{len(tracks)} tracks")


def cmd_lookup(args):
    track = inputs.make_track([args.artist], args.title, args.duration)
    cache = Cache(args.db)
    client = Client()
    ranked = scout.ranked_candidates(client, cache, track, args.ttl_days, args.refresh)
    if not ranked:
        print("no candidates")
    for score, c in ranked:
        ptype, price = pricing.classify(c)
        print(f"{score:.3f} {scout.match.status(score):8} {pricing.label(ptype, price, c.currency):16} "
              f"{c.artist} — {c.title} ({c.duration_s or '?'}s)\n      {c.url}")


def cmd_run(args):
    tracks = load_tracks(args)
    cache = Cache(args.db)
    cache.put_inputs(tracks)
    todo = [t for t in tracks if args.refresh or not is_fresh(cache.result_checked_at(t.key), args.ttl_days)]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(tracks)} tracks, {len(tracks) - len(todo)} already checked, {len(todo)} to do")
    client, hits, failed = Client(), 0, 0
    try:
        for i, t in enumerate(todo, 1):
            try:
                r = scout.check_track(client, cache, t, args.ttl_days, args.refresh)
            except httpx.HTTPError as e:
                # no result stored, so the next run retries this track
                failed += 1
                print(f"\nskipped {', '.join(t.artists)} - {t.title}: {e}", file=sys.stderr)
                continue
            cache.put_result(t.key, r)
            hits += r["status"] == "match" and r.get("price_type") in ("free", "nyp_zero", "nyp_min")
            print(f"\r{i}/{len(todo)}  free/NYP hits: {hits}  ", end="", flush=True)
    except KeyboardInterrupt:
        print("\nstopped; run again to resume")
        return 130
    print()
    if failed:
        print(f"{failed} tracks failed (network); run again to retry them")
    print(report.stats(cache.rows()))


def cmd_report(args):
    only = set(args.only.split(",")) if args.only else None
    rows = report.select(Cache(args.db).rows(), only)
    report.write_csv(rows, args.out)
    print(f"wrote {len(rows)} rows to {args.out}")


def cmd_override(args):
    cache = Cache(args.db)
    track = cache.get_input(args.key)
    if track is None:
        return f"unknown key {args.key} (run `scout run` first; keys are in the report)"
    cache.set_override(args.key, None if args.none else args.url)
    r = scout.check_track(Client(), cache, track, args.ttl_days)
    cache.put_result(track.key, r)
    print(f"{args.key}: {r['status']} {r.get('price_type') or ''}")


def cmd_stats(args):
    print(report.stats(Cache(args.db).rows()))


def cmd_gui(args):
    from .gui import main as gui_main
    return gui_main()


def main(argv=None):
    p = argparse.ArgumentParser(prog="scout", description=__doc__)
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"cache file (default {DEFAULT_DB})")
    sub = p.add_subparsers(dest="cmd", required=True)

    def source(sp):
        sp.add_argument("--csv", help="CSV with artist,title[,duration_s,isrc,spotify_id] instead of the Assistant")
        sp.add_argument("--sgh", action="store_true", help="read from the Subgenre Assistant (the default)")
        sp.add_argument("--playlist", action="append", help="playlist id (repeatable; 'liked' for Liked Songs)")

    def ttl(sp):
        sp.add_argument("--ttl-days", type=float, default=30)

    sp = sub.add_parser("inputs", help="print the tracks that would be scouted")
    source(sp)
    sp.set_defaults(fn=cmd_inputs)

    sp = sub.add_parser("lookup", help="search one track and show candidates")
    sp.add_argument("artist")
    sp.add_argument("title")
    sp.add_argument("--duration", type=float, help="seconds")
    sp.add_argument("--refresh", action="store_true")
    ttl(sp)
    sp.set_defaults(fn=cmd_lookup)

    sp = sub.add_parser("run", help="scout all tracks (resumable)")
    source(sp)
    sp.add_argument("--limit", type=int)
    sp.add_argument("--refresh", action="store_true", help="ignore cached searches, pages and results")
    ttl(sp)
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("report", help="write the CSV report")
    sp.add_argument("--out", default="report.csv")
    sp.add_argument("--only", help="comma list of price types/statuses, e.g. free,nyp_zero,nyp_min,review")
    sp.set_defaults(fn=cmd_report)

    sp = sub.add_parser("override", help="fix a match by hand; always wins")
    sp.add_argument("key")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--url", help="the right Bandcamp track URL")
    g.add_argument("--none", action="store_true", help="not on Bandcamp")
    ttl(sp)
    sp.set_defaults(fn=cmd_override)

    sp = sub.add_parser("stats", help="counts by status and price type")
    sp.set_defaults(fn=cmd_stats)

    sp = sub.add_parser("gui", help="settings window")
    sp.set_defaults(fn=cmd_gui)

    args = p.parse_args(argv)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    try:
        return args.fn(args)
    except inputs.InputError as e:
        return f"error: {e}"


if __name__ == "__main__":
    sys.exit(main())
