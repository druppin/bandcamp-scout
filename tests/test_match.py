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
