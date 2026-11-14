"""~/.config/bandcamp-scout/config.toml: read with tomllib, written by hand (flat, known keys only)."""
import json
import os
import tomllib
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "bandcamp-scout" / "config.toml"
DEFAULT_SGH_URL = "http://127.0.0.1:3000/api/v1"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def defaults() -> dict:
    return {
        "sgh": {"url": DEFAULT_SGH_URL, "api_key": ""},
        "input": {"playlists": ["liked"], "mixxx_db": ""},
        "schedule": {"mode": "manual", "weekday": "Mon", "time": "09:00"},
    }


def load(path: Path = CONFIG_PATH) -> tuple[dict, bool]:
    """Returns (config, existed). Env SGH_URL / SGH_API_KEY override the file."""
    cfg = defaults()
    existed = path.exists()
    if existed:
        for section, values in tomllib.loads(path.read_text()).items():
            if section in cfg and isinstance(values, dict):
                cfg[section].update(values)
    cfg["sgh"]["url"] = os.environ.get("SGH_URL") or cfg["sgh"]["url"]
    cfg["sgh"]["api_key"] = os.environ.get("SGH_API_KEY") or cfg["sgh"]["api_key"]
    return cfg, existed


def _value(v) -> str:
    # JSON strings/arrays of strings are valid TOML
    return json.dumps(v, ensure_ascii=False)


def save(cfg: dict, path: Path = CONFIG_PATH) -> None:
    lines = []
    for section, values in cfg.items():
        lines.append(f"[{section}]")
        lines += [f"{k} = {_value(v)}" for k, v in values.items()]
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines))
    os.chmod(tmp, 0o600)  # holds the API key
    tmp.replace(path)
