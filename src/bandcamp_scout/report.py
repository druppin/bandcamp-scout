"""CSV report and stats from the cache rows."""
import csv
from collections import Counter

COLUMNS = ["key", "artist", "title", "status", "score", "price_type", "price", "currency",
           "track_url", "album_url", "album_price_type", "album_price", "checked_at"]
_PRICE_ORDER = {"free": 0, "nyp_zero": 1, "nyp_min": 2, "paid": 3, "album_only": 4}
_STATUS_ORDER = {"match": 0, "review": 1, "no_match": 2}


def sort_key(r):
    # matched tracks by price (free first), then review, then no match
    return (_STATUS_ORDER.get(r["status"], 3), _PRICE_ORDER.get(r["price_type"], 5), -(r["score"] or 0))


def select(rows, only=None):
    """only: set of price types and/or statuses; a price type only counts for matches."""
    if not only:
        return rows
    return [r for r in rows if r["status"] in only or (r["status"] == "match" and r["price_type"] in only)]


def write_csv(rows, out):
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=sort_key):
            w.writerow({**r, "artist": ", ".join(r["artists"])})


def stats(rows) -> str:
    by_status = Counter(r["status"] for r in rows)
    by_price = Counter(r["price_type"] for r in rows if r["status"] == "match")
    by_price_review = Counter(r["price_type"] for r in rows if r["status"] == "review")
    lines = [f"tracks checked: {len(rows)}"]
    lines += [f"  {s:9} {by_status.get(s, 0)}" for s in ("match", "review", "no_match")]
    lines.append("matched, by price type:")
    lines += [f"  {p:12} {n}" for p, n in by_price.most_common()]
    if by_price_review:
        lines.append("in review, by price type:")
        lines += [f"  {p:12} {n}" for p, n in by_price_review.most_common()]
    return "\n".join(lines)
