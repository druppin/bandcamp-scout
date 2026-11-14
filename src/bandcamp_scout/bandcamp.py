"""The only module that knows Bandcamp's URLs and data shapes. See docs/findings.md."""
import html
import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urljoin

SEARCH_URL = "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic"
_TRALBUM = re.compile(r'data-tralbum="([^"]*)"')
_CURRENCY = re.compile(r'data-band-currency="([A-Z]{3})"')


class ParseError(Exception):
    pass


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    artist: str  # band_name: the account the track is on, often a label or a bootlegger
    album: str | None


@dataclass(frozen=True)
class Candidate:
    url: str
    item_type: str  # "track" | "album"
    artist: str
    title: str
    duration_s: float | None
    album_url: str | None
    currency: str | None
    download_pref: int | None  # 1 = free, 2 = paid (incl. NYP), None = can't buy this item alone
    minimum_price: float | None
    set_price: float | None
    is_set_price: bool  # fixed price, no "or more"
    downloadable: bool | None
    free_download_page: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, s: str) -> "Candidate":
        return cls(**json.loads(s))


def search_body(query: str) -> dict:
    return {"search_text": query, "search_filter": "t", "full_page": False}


def parse_search(data: dict, limit: int = 5) -> list[SearchHit]:
    results = (data.get("auto") or {}).get("results") or []
    return [SearchHit(r["item_url_path"], r["name"], r.get("band_name") or "", r.get("album_name"))
            for r in results if r.get("type") == "t" and r.get("item_url_path")][:limit]


def parse_release(page: str, url: str) -> Candidate:
    m = _TRALBUM.search(page)
    if not m:
        raise ParseError(f"no data-tralbum on {url}")
    d = json.loads(html.unescape(m.group(1)))
    cur = d.get("current") or {}
    tracks = d.get("trackinfo") or []
    first = tracks[0] if tracks else {}
    cm = _CURRENCY.search(page)
    item_type = d.get("item_type") or ""
    url = d.get("url") or url
    return Candidate(
        url=url,
        item_type=item_type,
        artist=d.get("artist") or "",
        title=cur.get("title") or first.get("title") or "",
        duration_s=first.get("duration") if item_type == "track" else None,
        album_url=urljoin(url, d["album_url"]) if d.get("album_url") else None,
        currency=cm.group(1) if cm else None,
        download_pref=cur.get("download_pref"),
        minimum_price=cur.get("minimum_price"),
        set_price=cur.get("set_price"),
        is_set_price=bool(cur.get("is_set_price")),
        downloadable=first.get("is_downloadable") if item_type == "track" else None,
        free_download_page=bool(d.get("freeDownloadPage")),
    )


def search(client, query: str) -> dict:
    return client.post(SEARCH_URL, json=search_body(query)).json()


def fetch_release(client, url: str) -> Candidate:
    return parse_release(client.get(url).text, url)
