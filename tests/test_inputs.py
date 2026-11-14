import sqlite3
import tempfile
import unittest
from pathlib import Path

import httpx

from bandcamp_scout import inputs

SONG = {"id": "sp1", "isrc": "GBX1", "title": "Archangel", "artists": ["Burial"], "durationMs": 238000, "album": "Untrue"}
LOCAL = {"id": None, "isrc": None, "title": "Dub", "artists": ["Someone"], "durationMs": None, "album": None}
OTHER = {"id": "sp2", "isrc": "GBX2", "title": "Even If", "artists": ["Calibre"], "durationMs": 454000, "album": None}


def sgh(status=200):
    def handler(req):
        if req.headers.get("Authorization") != "Bearer sgh_good" or status == 401:
            return httpx.Response(401, json={"error": "bad key"})
        path = req.url.path
        if path.endswith("/playlists"):
            return httpx.Response(200, json={"playlists": [{"id": "liked", "name": "Liked Songs"}, {"id": "p1", "name": "DnB"}]})
        if path.endswith("/playlists/liked/tracks"):
            return httpx.Response(200, json={"playlist": {}, "tracks": [SONG, LOCAL]})
        if path.endswith("/playlists/p1/tracks"):
            return httpx.Response(200, json={"playlist": {}, "tracks": [SONG, OTHER]})
        return httpx.Response(404, json={"error": "nope"})
    return httpx.MockTransport(handler)


class Sgh(unittest.TestCase):
    URL = "http://127.0.0.1:3000/api/v1"

    def test_all_playlists_dedupes(self):
        tracks = inputs.load_sgh(self.URL, "sgh_good", "all", transport=sgh())
        self.assertEqual([t.title for t in tracks], ["Archangel", "Dub", "Even If"])
        self.assertEqual(tracks[0], inputs.InputTrack("sp1", ("Burial",), "Archangel", 238.0, "GBX1", "sp1"))
        self.assertTrue(tracks[1].key.startswith("h:"))

    def test_chosen_playlist(self):
        self.assertEqual(len(inputs.load_sgh(self.URL, "sgh_good", ["liked"], transport=sgh())), 2)

    def test_errors(self):
        with self.assertRaisesRegex(inputs.InputError, "401"):
            inputs.load_sgh(self.URL, "sgh_bad", ["liked"], transport=sgh())
        with self.assertRaisesRegex(inputs.InputError, "API key"):
            inputs.load_sgh(self.URL, "", ["liked"])
        with self.assertRaisesRegex(inputs.InputError, "running"):
            inputs.load_sgh("http://127.0.0.1:9/api/v1", "sgh_good", ["liked"])  # nothing listens on 9


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.p = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_csv(self):
        f = self.p / "t.csv"
        f.write_text("artist,title,duration_s\nBurial; Kode9,Archangel,238\nBurial; Kode9,Archangel,238\n,,\n")
        tracks = inputs.load_csv(f)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].artists, ("Burial", "Kode9"))
        f.write_text("name\nx\n")
        with self.assertRaises(inputs.InputError):
            inputs.load_csv(f)

    def test_mixxx_and_merge(self):
        db = self.p / "mixxxdb.sqlite"
        con = sqlite3.connect(db)
        con.executescript("""
            CREATE TABLE track_locations (id INTEGER PRIMARY KEY, location TEXT, fs_deleted INTEGER);
            CREATE TABLE library (id INTEGER PRIMARY KEY, artist TEXT, title TEXT, duration REAL,
                                  location INTEGER, mixxx_deleted INTEGER);
            INSERT INTO track_locations VALUES (1,'/a.mp3',0),(2,'/b.mp3',0),(3,'/c.mp3',1);
            INSERT INTO library VALUES (1,'Burial','Archangel',238,1,0),(2,'Calibre','Mr Right On',300,2,0),
                                       (3,'Gone','File',1,3,0),(4,'Deleted','Row',1,1,1);""")
        con.commit()
        con.close()
        mixxx = inputs.load_mixxx(db)
        self.assertEqual([t.title for t in mixxx], ["Archangel", "Mr Right On"])
        merged = inputs.merge([inputs.make_track(["Burial"], "Archangel", spotify_id="sp1")], mixxx)
        self.assertEqual([t.key for t in merged][0], "sp1")
        self.assertEqual(len(merged), 2)
