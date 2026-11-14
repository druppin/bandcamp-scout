"""`scout gui`: edit config.toml. Needs the `gui` extra (PySide6)."""
import sys

from PySide6.QtCore import QProcess, Qt, QTime
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QTimeEdit, QVBoxLayout, QWidget)

from . import config, inputs, timer


class Settings(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("bandcamp-scout settings")
        self.cfg, _ = config.load()
        lay = QVBoxLayout(self)

        conn = QGroupBox("Subgenre Assistant")
        f = QFormLayout(conn)
        self.url = QLineEdit(self.cfg["sgh"]["url"])
        self.key = QLineEdit(self.cfg["sgh"]["api_key"])
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        test = QPushButton("Test")
        test.clicked.connect(self.load_playlists)
        self.conn_status = QLabel()
        f.addRow("URL", self.url)
        f.addRow("API key", self.key)
        f.addRow(test, self.conn_status)
        lay.addWidget(conn)

        box = QGroupBox("Playlists to scan")
        v = QVBoxLayout(box)
        self.all = QCheckBox("All playlists")
        self.all.setChecked(self.cfg["input"]["playlists"] == "all")
        self.all.toggled.connect(lambda on: self.list.setEnabled(not on))
        self.list = QListWidget()
        self.list.setEnabled(not self.all.isChecked())
        v.addWidget(self.all)
        v.addWidget(self.list)
        h = QHBoxLayout()
        self.use_mixxx = QCheckBox("Also scan Mixxx library")
        self.mixxx = QLineEdit(self.cfg["input"].get("mixxx_db") or "")
        self.use_mixxx.setChecked(bool(self.mixxx.text()))
        pick = QPushButton("…")
        pick.clicked.connect(self.pick_mixxx)
        h.addWidget(self.use_mixxx)
        h.addWidget(self.mixxx)
        h.addWidget(pick)
        v.addLayout(h)
        lay.addWidget(box)

        sched = QGroupBox("Schedule")
        h = QHBoxLayout(sched)
        self.mode = QComboBox()
        self.mode.addItems(["manual", "weekly"])
        self.mode.setCurrentText(self.cfg["schedule"]["mode"])
        self.weekday = QComboBox()
        self.weekday.addItems(config.WEEKDAYS)
        self.weekday.setCurrentText(self.cfg["schedule"]["weekday"])
        self.time = QTimeEdit(QTime.fromString(self.cfg["schedule"]["time"], "HH:mm"))
        self.time.setDisplayFormat("HH:mm")
        self.next = QLabel()
        for w in (self.mode, self.weekday, self.time, self.next):
            h.addWidget(w)
        lay.addWidget(sched)

        h = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self.save)
        run = QPushButton("Run now")
        run.clicked.connect(self.run_now)
        h.addWidget(save)
        h.addWidget(run)
        lay.addLayout(h)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(500)
        lay.addWidget(self.log)

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyRead.connect(lambda: self.log.insertPlainText(
            bytes(self.proc.readAll()).decode(errors="replace").replace("\r", "\n")))
        self.show_next()
        self.load_playlists()

    def load_playlists(self):
        chosen = self.cfg["input"]["playlists"]
        chosen = set(chosen) if isinstance(chosen, list) else set()
        self.list.clear()
        try:
            playlists = inputs.list_playlists(self.url.text(), self.key.text())
        except Exception as e:
            self.conn_status.setText(f"Not connected: {type(e).__name__}. Is the Assistant running?")
            playlists = [{"id": "liked", "name": "Liked Songs"}]
        else:
            self.conn_status.setText(f"Connected, {len(playlists)} playlists")
            if not any(p["id"] == "liked" for p in playlists):
                playlists.insert(0, {"id": "liked", "name": "Liked Songs"})
        playlists.sort(key=lambda p: p["id"] != "liked")  # Liked Songs at the top
        for p in playlists:
            item = QListWidgetItem(p.get("name") or p["id"])
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            item.setCheckState(Qt.CheckState.Checked if p["id"] in chosen else Qt.CheckState.Unchecked)
            self.list.addItem(item)

    def pick_mixxx(self):
        path, _ = QFileDialog.getOpenFileName(self, "mixxxdb.sqlite copy", "", "SQLite (*.sqlite *.db)")
        if path:
            self.mixxx.setText(path)
            self.use_mixxx.setChecked(True)

    def chosen_playlists(self):
        if self.all.isChecked():
            return "all"
        items = (self.list.item(i) for i in range(self.list.count()))
        return [i.data(Qt.ItemDataRole.UserRole) for i in items if i.checkState() == Qt.CheckState.Checked]

    def save(self):
        self.cfg["sgh"] = {"url": self.url.text().strip(), "api_key": self.key.text().strip()}
        self.cfg["input"] = {"playlists": self.chosen_playlists(),
                             "mixxx_db": self.mixxx.text() if self.use_mixxx.isChecked() else ""}
        self.cfg["schedule"] = {"mode": self.mode.currentText(), "weekday": self.weekday.currentText(),
                                "time": self.time.time().toString("HH:mm")}
        config.save(self.cfg)
        try:
            timer.apply(self.cfg["schedule"])
        except OSError as e:
            QMessageBox.warning(self, "Schedule", f"Saved settings, but the timer failed: {e}")
        self.show_next()

    def show_next(self):
        nxt = timer.next_run() if self.cfg["schedule"]["mode"] == "weekly" else ""
        self.next.setText(f"next: {nxt}" if nxt else "")

    def run_now(self):
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            return
        self.log.clear()
        self.proc.start(sys.executable, ["-m", "bandcamp_scout.cli", "run"])


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    w = Settings()
    w.resize(520, 640)
    w.show()
    return app.exec()
