"""Glue: search -> fetch top candidates -> score -> classify, going through the cache."""
import httpx

from . import bandcamp, match, pricing
from .bandcamp import Candidate, ParseError

PAGES_PER_TRACK = 2  # fetch at most this many result pages per track (each is one request)


def query_for(track) -> str:
    title, _ = match.split_title(track.title)
    return match.normalize(f"{track.artists[0] if track.artists else ''} {title}")


def get_search(client, cache, query, ttl_days, refresh):
    data = None if refresh else cache.get_search(query, ttl_days)
    if data is None:
        data = bandcamp.search(client, query)
        cache.put_search(query, data)
    return bandcamp.parse_search(data)


def get_candidate(client, cache, url, ttl_days, refresh) -> Candidate | None:
    cached = None if refresh else cache.get_page(url, ttl_days)
    if cached:
        return Candidate.from_json(cached)
    try:
        c = bandcamp.fetch_release(client, url)
    except (ParseError, httpx.HTTPStatusError):
        return None
    cache.put_page(url, c.to_json())
    return c


def score_candidate(track, c: Candidate) -> float:
    return match.score(track.artists, track.title, track.duration_s, c.artist, c.title, c.duration_s)


def ranked_candidates(client, cache, track, ttl_days=30, refresh=False) -> list[tuple[float, Candidate]]:
    hits = get_search(client, cache, query_for(track), ttl_days, refresh)
    # rank by name only (search results carry no duration), then fetch the best few pages
    hits.sort(key=lambda h: -match.score(track.artists, track.title, None, h.artist, h.title, None))
    out = []
    for h in hits[:PAGES_PER_TRACK]:
        c = get_candidate(client, cache, h.url, ttl_days, refresh)
        if c:
            out.append((score_candidate(track, c), c))
    return sorted(out, key=lambda x: -x[0])


def result_for(client, cache, c: Candidate, score: float, status: str, ttl_days, refresh) -> dict:
    price_type, price = pricing.classify(c)
    r = {"track_url": c.url, "album_url": c.album_url, "status": status, "score": score,
         "price_type": price_type, "price": price, "currency": c.currency}
    if c.album_url and status != "no_match":
        album = get_candidate(client, cache, c.album_url, ttl_days, refresh)
        if album:
            r["album_price_type"], r["album_price"] = pricing.classify(album)
            if price_type == "album_only":
                r["price"] = r["album_price"]
    return r


def check_track(client, cache, track, ttl_days=30, refresh=False) -> dict:
    override = cache.get_override(track.key)
    if override:
        url = override[0]
        if url is None:
            return {"status": "no_match", "score": 0.0}
        c = get_candidate(client, cache, url, ttl_days, refresh)
        if c is None:
            return {"track_url": url, "status": "review", "score": 0.0, "price_type": "unknown"}
        return result_for(client, cache, c, 1.0, "match", ttl_days, refresh)
    ranked = ranked_candidates(client, cache, track, ttl_days, refresh)
    if not ranked:
        return {"status": "no_match", "score": 0.0}
    score, best = ranked[0]
    # near-misses keep their candidate so they can be looked at
    return result_for(client, cache, best, score, match.status(score), ttl_days, refresh)
