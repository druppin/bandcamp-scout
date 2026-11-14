import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # gui extra not installed
    QApplication = None

from bandcamp_scout import config


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class Window(unittest.TestCase):
    def test_opens_without_assistant(self):
        from bandcamp_scout import gui
        app = QApplication.instance() or QApplication([])
        with mock.patch.object(gui.config, "load", return_value=(config.defaults(), False)), \
             mock.patch.object(gui.inputs, "list_playlists", side_effect=ConnectionError), \
             mock.patch.object(gui.timer, "next_run", return_value=""):
            w = gui.Settings()
        self.assertIn("Not connected", w.conn_status.text())
        self.assertEqual(w.list.count(), 1)
        self.assertEqual(w.chosen_playlists(), ["liked"])
        w.close()
        app.processEvents()
