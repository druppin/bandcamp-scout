import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bandcamp_scout import config, timer


class Config(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.toml"

    def tearDown(self):
        self.dir.cleanup()

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_missing_file_means_liked_only(self):
        cfg, existed = config.load(self.path)
        self.assertFalse(existed)
        self.assertEqual(cfg["input"]["playlists"], ["liked"])

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_roundtrip(self):
        cfg = config.defaults()
        cfg["sgh"]["api_key"] = 'sgh_"quoted"'
        cfg["input"] = {"playlists": ["liked", "37i9"], "mixxx_db": "/home/x/Mïxxx/mixxxdb.sqlite"}
        cfg["schedule"] = {"mode": "weekly", "weekday": "Fri", "time": "21:30"}
        config.save(cfg, self.path)
        self.assertEqual(config.load(self.path), (cfg, True))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        cfg["input"]["playlists"] = "all"
        config.save(cfg, self.path)
        self.assertEqual(config.load(self.path)[0]["input"]["playlists"], "all")

    @mock.patch.dict(os.environ, {"SGH_API_KEY": "sgh_env"}, clear=True)
    def test_env_overrides(self):
        self.assertEqual(config.load(self.path)[0]["sgh"]["api_key"], "sgh_env")


class Timer(unittest.TestCase):
    def test_weekly_installs_and_manual_removes(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []
            timer.apply({"mode": "weekly", "weekday": "Fri", "time": "21:30"}, Path(d), lambda *a: calls.append(a))
            text = (Path(d) / "bandcamp-scout.timer").read_text()
            self.assertIn("OnCalendar=Fri *-*-* 21:30:00", text)
            self.assertIn(("enable", "--now", "bandcamp-scout.timer"), calls)
            timer.apply({"mode": "manual"}, Path(d), lambda *a: calls.append(a))
            self.assertEqual(list(Path(d).iterdir()), [])
            self.assertIn(("disable", "--now", "bandcamp-scout.timer"), calls)

    def test_next_run_parse(self):
        out = ("NEXT                         LEFT LAST PASSED UNIT                 ACTIVATES\n"
               "Fri 2026-11-20 21:30:00 CET  5 days -   -      bandcamp-scout.timer bandcamp-scout.service\n")
        fake = lambda *a: mock.Mock(stdout=out)
        self.assertEqual(timer.next_run(fake), "Fri 2026-11-20 21:30:00 CET")
