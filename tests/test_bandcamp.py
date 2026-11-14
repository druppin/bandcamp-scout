import dataclasses
import json
import unittest

from bandcamp_scout import bandcamp, pricing
from tests.helpers import PAGES, fixture


def parse(name):
    url = next(u for u, n in PAGES.items() if n == name)
    return bandcamp.parse_release(fixture(name), url)


class ParseAndClassify(unittest.TestCase):
    def test_search(self):
        hits = bandcamp.parse_search(json.loads(fixture("search_burial_archangel.json")))
        self.assertEqual(len(hits), 5)
        self.assertEqual(hits[0].url, "https://oylumtanis.bandcamp.com/track/burial-archangel")
        self.assertEqual(hits[0].artist, "oylumtanis")

    def test_fixtures(self):
        expected = {
            "track_free.html": ("free", 0.0),
            "track_nyp_zero.html": ("nyp_zero", 0.0),
            "track_nyp_min.html": ("nyp_min", 1.5),
            "track_subscriber_only.html": ("album_only", None),
            "album_subscriber_only.html": ("nyp_zero", 0.0),
            "album_nyp_min.html": ("nyp_min", 3.0),
        }
        for name, want in expected.items():
            with self.subTest(name):
                self.assertEqual(pricing.classify(parse(name)), want)

    def test_fields(self):
        c = parse("track_nyp_min.html")
        self.assertEqual((c.artist, c.title, c.currency), ("Calibre", "Even If", "GBP"))
        self.assertAlmostEqual(c.duration_s, 454.253)
        self.assertEqual(c.album_url, "https://calibre.bandcamp.com/album/even-if")
        self.assertEqual(parse("track_subscriber_only.html").album_url, "https://xtrica.bandcamp.com/album/fixated")

    def test_fixed_price_and_unknown(self):
        # no fixed-price page found in Phase 0; this is the nyp_min page with the flag set
        c = dataclasses.replace(parse("track_nyp_min.html"), is_set_price=True)
        self.assertEqual(pricing.classify(c), ("paid", 1.5))
        self.assertEqual(pricing.classify(dataclasses.replace(c, is_set_price=False, minimum_price=None)),
                         ("unknown", None))
        self.assertEqual(pricing.classify(dataclasses.replace(c, download_pref=7)), ("unknown", None))
        self.assertEqual(pricing.classify(dataclasses.replace(c, download_pref=None, downloadable=False,
                                                              album_url=None)), ("not_for_sale", None))

    def test_no_tralbum(self):
        with self.assertRaises(bandcamp.ParseError):
            bandcamp.parse_release("<html></html>", "https://x.bandcamp.com/track/y")

    def test_candidate_json_roundtrip(self):
        c = parse("track_free.html")
        self.assertEqual(bandcamp.Candidate.from_json(c.to_json()), c)
