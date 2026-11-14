import json
import unittest

from bandcamp_scout import match
from tests.helpers import fixture


class Normalize(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(match.normalize("  Sigur Rós & Friends!! "), "sigur ros and friends")

    def test_split_title(self):
        cases = {
            "Glue (Original Mix)": ("glue", None),
            "Glue - Original Mix": ("glue", None),
            "Glue (Skrillex Remix) [Ninja Tune]": ("glue", "skrillex remix"),
            "Glue - Extended Mix": ("glue", "extended mix"),
            "Glue feat. Someone": ("glue", None),
            "Glue (feat. Someone) [VIP]": ("glue", "vip"),
            "Glue - 2019 Remaster": ("glue", None),
        }
        for title, want in cases.items():
            with self.subTest(title):
                self.assertEqual(match.split_title(title), want)

    def test_candidate_names(self):
        self.assertEqual(match.candidate_names("Noneohone", "Burial- Archangel (Noneohone UKG Edit)"),
                         (["noneohone", "burial"], "archangel", "noneohone ukg edit"))
        self.assertEqual(match.candidate_names("X", "Hip-Hop Song"), (["x"], "hip hop song", None))

    def test_artist_names_are_whole(self):
        self.assertEqual(match.artist_names(["DJ Marky & S.P.Y", "Mura Masa x Rihanna", "X", "The Misfits"]),
                         ["dj marky", "s p y", "mura masa", "rihanna", "x", "misfits"])
        self.assertNotEqual(match.status(match.score(["Rush"], "Xanadu", 665, "Gush", "Xanadu", 666)), "match")
        self.assertEqual(match.split_title("Crazy Train (8-bit)")[1], "8 bit")
        self.assertEqual(match.split_title("Still the One (live)")[1], "live")
        # cover bands and name-alikes no longer count as the artist
        self.assertEqual(match.status(match.score(["Zim"], "Touch Me", 180, "Gera Zim Zum", "Touch Me", 174)), "no_match")
        self.assertNotEqual(match.status(match.score(["Misfits"], "Astro Zombies", 131, "8-Bit Misfits", "Astro Zombies", 140)), "match")

    def test_other_accounts_upload_needs_same_length(self):
        repost = dict(artists=["Coldplay"], title="Clocks", bc_artist="Artists Project", bc_title="Coldplay - Clocks")
        self.assertEqual(match.status(match.score(duration_s=308, bc_duration_s=302, **repost)), "review")
        self.assertEqual(match.status(match.score(duration_s=208, bc_duration_s=208, **{**repost, "bc_artist": "Garage Shared"})), "match")

    def test_title_subset_is_not_a_match(self):
        s = match.score(["JOYRYDE"], "ON FIRE", 200, "Joyride and Crabbz", "Chestnuts Roasting On An Open Fire", 200)
        self.assertEqual(match.status(s), "no_match")

    def test_duration(self):
        self.assertEqual(match.duration_score(200, 203), 1.0)
        self.assertEqual(match.duration_score(200, 215), 0.0)
        self.assertEqual(match.duration_score(None, 215), 0.5)

    def test_version_mismatch_caps(self):
        s = match.score(["Four Tet"], "Baby", 264, "Four Tet", "Baby (Tony Romera Remix)", 264)
        self.assertLessEqual(s, match.VERSION_CAP)


class LabeledSet(unittest.TestCase):
    def test_no_false_matches(self):
        pairs = json.loads(fixture("labeled.json"))["pairs"]
        tp = fp = fn = 0
        for p in pairs:
            s = match.score(p["artists"], p["title"], p["duration_s"], p["bc_artist"], p["bc_title"], p["bc_duration_s"])
            hit = match.status(s) == "match"
            tp += hit and p["correct"]
            fp += hit and not p["correct"]
            fn += not hit and p["correct"]
            if hit != p["correct"]:
                print(f"\n  {'FALSE MATCH' if hit else 'missed'}: {s:.3f} {p['title']!r} vs {p['bc_title']!r}")
        print(f"\n  labeled set: precision {tp / max(tp + fp, 1):.2f}, recall {tp / max(tp + fn, 1):.2f} ({len(pairs)} pairs)")
        self.assertEqual(fp, 0)
