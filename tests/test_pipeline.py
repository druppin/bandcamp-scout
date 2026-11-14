import csv
import tempfile
import unittest
from pathlib import Path

import httpx

from bandcamp_scout import report, scout
from bandcamp_scout.cache import Cache
from bandcamp_scout.http import Client
from bandcamp_scout.inputs import make_track
from tests.helpers import bandcamp_transport

EDIT = make_track(["Burial", "Noneohone"], "Archangel (Noneohone UKG Edit)", 281.0)
ORIGINAL = make_track(["Burial"], "Archangel", 238.0)


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cache = Cache(Path(self.dir.name) / "scout.db")
        self.log = []
        self.client = Client(delay=0, jitter=0, transport=bandcamp_transport(self.log))
        self.cache.put_inputs([EDIT, ORIGINAL])

    def tearDown(self):
        self.cache.close()
        self.dir.cleanup()

    def check(self, t, **kw):
        r = scout.check_track(self.client, self.cache, t, **kw)
        self.cache.put_result(t.key, r)
        return r

    def test_match_then_cached(self):
        r = self.check(EDIT)
        self.assertEqual((r["status"], r["price_type"], r["currency"]), ("match", "nyp_zero", "AUD"))
        self.assertTrue(r["track_url"].startswith("https://noneohone.bandcamp.com/"))
        n = len(self.log)
        self.check(EDIT)
        self.assertEqual(len(self.log), n, "second check should be served from the cache")
        self.check(EDIT, refresh=True)
        self.assertGreater(len(self.log), n)

    def test_reupload_goes_to_review_not_match(self):
        r = self.check(ORIGINAL)  # oylumtanis' 3:00 reupload vs the 3:58 original
        self.assertEqual(r["status"], "review")
        self.assertEqual(r["price_type"], "free")

    def test_override_wins_and_survives_refresh(self):
        self.cache.set_override(ORIGINAL.key, None)
        self.assertEqual(self.check(ORIGINAL, refresh=True)["status"], "no_match")
        self.cache.set_override(ORIGINAL.key, "https://xtrica.bandcamp.com/track/subfocus")
        r = self.check(ORIGINAL, refresh=True)
        self.assertEqual((r["status"], r["price_type"], r["album_price_type"], r["price"]),
                         ("match", "album_only", "nyp_zero", 0.0))

    def test_report_and_stats(self):
        self.check(EDIT)
        self.check(ORIGINAL)
        rows = self.cache.rows()
        out = Path(self.dir.name) / "report.csv"
        report.write_csv(rows, out)
        lines = list(csv.DictReader(out.read_text().splitlines()))
        self.assertEqual([l["status"] for l in lines], ["match", "review"])
        self.assertEqual(lines[0]["artist"], "Burial, Noneohone")
        self.assertEqual(len(report.select(rows, {"free", "nyp_zero"})), 1)  # review row's 'free' doesn't count
        self.assertEqual(len(report.select(rows, {"review"})), 1)
        self.assertIn("match     1", report.stats(rows))

    def test_http_errors_drop_candidate(self):
        bad = Client(delay=0, jitter=0, retries=1, sleep=lambda s: None,
                     transport=httpx.MockTransport(lambda r: httpx.Response(
                         200, json={"auto": {"results": [{"type": "t", "name": "X", "band_name": "Y",
                                                          "item_url_path": "https://y.bandcamp.com/track/x"}]}})
                         if "autocomplete" in str(r.url) else httpx.Response(404)))
        self.assertEqual(scout.check_track(bad, self.cache, EDIT)["status"], "no_match")


    def test_redirect_loop_skips_candidate(self):
        def handler(r):
            if "autocomplete" in str(r.url):
                return httpx.Response(200, json={"auto": {"results": [
                    {"type": "t", "name": "Archangel (Noneohone UKG Edit)", "band_name": "Label",
                     "item_url_path": "https://music.label.com/track/x"},
                    {"type": "t", "name": "Burial- Archangel (Noneohone UKG Edit)", "band_name": "Noneohone",
                     "item_url_path": "https://noneohone.bandcamp.com/track/burial-archangel-noneohone-ukg-edit"}]}})
            if "label" in str(r.url):  # custom domain <-> bandcamp.com loop seen on music.monstercat.com
                other = "https://label.bandcamp.com/track/x" if "music." in str(r.url) else "https://music.label.com/track/x"
                return httpx.Response(303, headers={"Location": other})
            return bandcamp_transport([]).handle_request(r)
        c = Client(delay=0, jitter=0, transport=httpx.MockTransport(handler))
        r = scout.check_track(c, self.cache, EDIT)
        self.assertEqual((r["status"], r["price_type"]), ("match", "nyp_zero"))


    def test_offline_rescore_uses_cache_only(self):
        from bandcamp_scout import cli
        self.check(EDIT)
        self.cache.close()
        db = Path(self.dir.name) / "scout.db"
        self.cache = Cache(db)
        self.cache.put_inputs([make_track(["Nobody"], "Uncached")])  # its search isn't cached: skipped, not crashed
        self.cache.close()
        self.assertIsNone(cli.main(["--db", str(db), "run", "--offline"]))
        self.cache = Cache(db)
        # both Burial tracks share the cached search "burial archangel", so both re-score offline
        self.assertEqual(sorted(r["status"] for r in self.cache.rows()), ["match", "review"])


class Retries(unittest.TestCase):
    def test_backs_off_on_429_then_succeeds(self):
        replies, slept = [429, 503, 200], []
        c = Client(delay=0, jitter=0, sleep=slept.append,
                   transport=httpx.MockTransport(lambda r: httpx.Response(replies.pop(0))))
        self.assertEqual(c.get("https://x").status_code, 200)
        self.assertEqual(slept, [2, 4])

    def test_gives_up_after_retries(self):
        c = Client(delay=0, jitter=0, retries=2, sleep=lambda s: None,
                   transport=httpx.MockTransport(lambda r: httpx.Response(500)))
        with self.assertRaises(httpx.HTTPStatusError):
            c.get("https://x")
