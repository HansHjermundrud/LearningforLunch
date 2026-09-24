#!/usr/bin/env python3
"""Shared helpers for the learning system scripts.

Everything here is standard library only, so the hooks work on any machine
with python3. Paths come from learn.config.json at the repo root.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(
    os.environ.get("CLAUDE_PROJECT_DIR") or pathlib.Path(__file__).resolve().parent.parent
).resolve()
CONFIG_PATH = ROOT / "learn.config.json"

DEFAULTS = {
    "notesDir": "notes",
    "vizDir": "notes/viz",
    "reviewsDir": "notes/reviews",
    "exercisesDir": "exercises",
    "stateDir": "state",
    "timezone": "",
    "checkpointMinutes": 12,
}

_config_cache: dict | None = None


def config() -> dict:
    """Merged configuration (defaults + learn.config.json)."""
    global _config_cache
    if _config_cache is None:
        data = dict(DEFAULTS)
        if CONFIG_PATH.exists():
            try:
                loaded = json.loads(CONFIG_PATH.read_text("utf-8"))
                data.update({k: v for k, v in loaded.items() if not k.startswith("_")})
            except Exception as exc:  # noqa: BLE001
                print(f"warning: could not parse {CONFIG_PATH}: {exc}", file=sys.stderr)
        _config_cache = data
    return _config_cache


def resolve(p: str | os.PathLike) -> pathlib.Path:
    """Expand ~ and $VARS; make relative paths relative to the repo root."""
    text = os.path.expandvars(os.path.expanduser(str(p)))
    path = pathlib.Path(text)
    return path if path.is_absolute() else (ROOT / path)


def dir_path(key: str, create: bool = False) -> pathlib.Path:
    path = resolve(config()[key])
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def tz():
    name = config().get("timezone")
    if name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:  # noqa: BLE001
            pass
    return _dt.datetime.now().astimezone().tzinfo


def now() -> _dt.datetime:
    return _dt.datetime.now(tz())


def today() -> str:
    return now().date().isoformat()


def ts() -> str:
    """ISO timestamp with offset, second precision."""
    return now().replace(microsecond=0).isoformat()


def parse_ts(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz())
    return parsed.astimezone(tz())


def fmt_local(value: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    parsed = parse_ts(value)
    return parsed.strftime(fmt) if parsed else (value or "")


def date_add(date_iso: str, days: int) -> str:
    return (_dt.date.fromisoformat(date_iso) + _dt.timedelta(days=days)).isoformat()


def read_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text("utf-8"))
    except FileNotFoundError:
        return default
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return default


def write_json(path, data) -> None:
    """Atomic write so a crash mid-write never corrupts state."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, path)


def append_text(path, text: str) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "topic"


def rel(path) -> str:
    try:
        return str(pathlib.Path(path).resolve().relative_to(ROOT))
    except Exception:  # noqa: BLE001
        return str(path)


# --- state -----------------------------------------------------------------

STATE_DEFAULT = {"version": 1, "active_topic": None, "log_target": None, "topics": {}}


def state_path() -> pathlib.Path:
    return dir_path("stateDir") / "state.json"


def deck_path() -> pathlib.Path:
    return dir_path("stateDir") / "deck.json"


def load_state() -> dict:
    state = read_json(state_path(), None)
    if not isinstance(state, dict):
        state = {}
    for key, value in STATE_DEFAULT.items():
        state.setdefault(key, json.loads(json.dumps(value)))
    return state


def save_state(state: dict) -> None:
    write_json(state_path(), state)


def hook_log(message: str) -> None:
    """Best-effort diagnostics for hooks (never raises)."""
    try:
        log_dir = dir_path("stateDir") / ".log"
        log_dir.mkdir(parents=True, exist_ok=True)
        append_text(log_dir / "hooks.log", f"{ts()} {message}\n")
    except Exception:  # noqa: BLE001
        pass
