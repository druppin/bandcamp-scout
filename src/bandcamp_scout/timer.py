"""Weekly run via a systemd user timer. Kept separate so it can be swapped for the job queue later."""
import shutil
import subprocess
import sys
from pathlib import Path

UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
NAME = "bandcamp-scout"


def scout_command() -> str:
    exe = shutil.which("scout")
    return f"{exe} run" if exe else f"{sys.executable} -m bandcamp_scout.cli run"


def units(weekday: str, time: str) -> dict[str, str]:
    return {
        f"{NAME}.service": f"[Unit]\nDescription=bandcamp-scout weekly run\n\n"
                           f"[Service]\nType=oneshot\nExecStart={scout_command()}\n",
        f"{NAME}.timer": f"[Unit]\nDescription=bandcamp-scout weekly run\n\n"
                         f"[Timer]\nOnCalendar={weekday} *-*-* {time}:00\nPersistent=true\n\n"
                         f"[Install]\nWantedBy=timers.target\n",
    }


def _systemctl(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def apply(schedule: dict, unit_dir: Path = UNIT_DIR, systemctl=_systemctl) -> None:
    """Install the timer for mode 'weekly', remove it otherwise."""
    if schedule.get("mode") == "weekly":
        unit_dir.mkdir(parents=True, exist_ok=True)
        for name, text in units(schedule["weekday"], schedule["time"]).items():
            (unit_dir / name).write_text(text)
        systemctl("daemon-reload")
        systemctl("enable", "--now", f"{NAME}.timer")
    else:
        systemctl("disable", "--now", f"{NAME}.timer")
        for name in units("Mon", "00:00"):
            (unit_dir / name).unlink(missing_ok=True)
        systemctl("daemon-reload")


def next_run(systemctl=_systemctl) -> str:
    out = systemctl("list-timers", f"{NAME}.timer", "--no-pager").stdout.splitlines()
    return out[1].split("  ")[0].strip() if len(out) > 1 and NAME in out[1] else ""
