import json
from pathlib import Path

import httpx

FIX = Path(__file__).parent / "fixtures"

PAGES = {
    "https://oylumtanis.bandcamp.com/track/burial-archangel": "track_free.html",
    "https://noneohone.bandcamp.com/track/burial-archangel-noneohone-ukg-edit": "track_nyp_zero.html",
    "https://calibre.bandcamp.com/track/even-if": "track_nyp_min.html",
    "https://xtrica.bandcamp.com/track/subfocus": "track_subscriber_only.html",
    "https://xtrica.bandcamp.com/album/fixated": "album_subscriber_only.html",
    "https://fourtet.bandcamp.com/album/baby-love-cry": "album_nyp_min.html",
}


def fixture(name):
    return (FIX / name).read_text()


def bandcamp_transport(log):
    """Serves the saved search response for every search, saved pages by URL, 404 otherwise."""
    def handler(req):
        log.append(str(req.url))
        if "autocomplete_elastic" in str(req.url):
            return httpx.Response(200, json=json.loads(fixture("search_burial_archangel.json")))
        name = PAGES.get(str(req.url))
        return httpx.Response(200, text=fixture(name)) if name else httpx.Response(404)
    return httpx.MockTransport(handler)
