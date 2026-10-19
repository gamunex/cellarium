"""Einstellungen und eigene Angaben je Prefix (Name, Notiz, ausgeblendet, Runner)."""

import json
import os
import threading
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cellarium"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "cellarium"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "roots": ["~"],      # wo nach Prefixen gesucht wird
    "maxDepth": 6,       # wie tief unterhalb jeder Wurzel
    "exclude": [],       # Pfade, die übersprungen werden
    "meta": {},          # Prefix-Pfad -> {label, notes, hidden, runner}
}

_lock = threading.Lock()


def load() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **data}


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    tmp.replace(CONFIG_FILE)


def update_meta(path: str, changes: dict) -> dict:
    with _lock:
        cfg = load()
        meta = {**cfg["meta"].get(path, {}), **changes}
        meta = {k: v for k, v in meta.items() if v not in ("", None, False)}
        if meta:
            cfg["meta"][path] = meta
        else:
            cfg["meta"].pop(path, None)
        save(cfg)
        return meta


def drop_meta(path: str) -> None:
    with _lock:
        cfg = load()
        if cfg["meta"].pop(path, None) is not None:
            save(cfg)
