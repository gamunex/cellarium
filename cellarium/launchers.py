"""Fragt die Launcher, welcher Prefix zu welchem Spiel gehört.

Jede Funktion liefert Einträge der Form (prefix_pfad, ref). Ein Prefix ohne Ref gilt als verwaist.
Fehlt ein Launcher, kommt einfach nichts zurück.
"""

import json
import os
import re
import sqlite3
from pathlib import Path

HOME = Path.home()


def _real(p) -> str:
    return os.path.realpath(os.path.expanduser(str(p)))


# ---------- Steam ----------

def steam_roots() -> list[Path]:
    seen, roots = set(), []
    for p in (HOME / ".local/share/Steam", HOME / ".steam/steam",
              HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        if p.is_dir() and _real(p) not in seen:
            seen.add(_real(p))
            roots.append(Path(_real(p)))
    return roots


def steam_libraries() -> list[Path]:
    libs, seen = [], set()
    for root in steam_roots():
        candidates = [root]
        try:
            vdf = (root / "steamapps/libraryfolders.vdf").read_text(errors="replace")
            candidates += [Path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s+"([^"]+)"', vdf)]
        except OSError:
            pass
        for lib in candidates:
            if (lib / "steamapps").is_dir() and _real(lib) not in seen:
                seen.add(_real(lib))
                libs.append(Path(_real(lib)))
    return libs


def steam():
    names = {}
    libs = steam_libraries()
    for lib in libs:
        for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
            try:
                m = re.search(r'"name"\s+"([^"]*)"', acf.read_text(errors="replace"))
            except OSError:
                continue
            if m:
                names[acf.stem.split("_", 1)[1]] = m.group(1)
    for lib in libs:
        compat = lib / "steamapps/compatdata"
        if not compat.is_dir():
            continue
        for d in compat.iterdir():
            pfx = d / "pfx"
            if not (pfx / "system.reg").is_file():
                continue
            appid = d.name
            if appid in names:
                ref = {"launcher": "Steam", "title": names[appid], "detail": f"AppID {appid}"}
            elif appid == "0":
                ref = {"launcher": "Steam", "title": "Steam-Standardprefix", "detail": "AppID 0"}
            elif len(appid) > 8:
                # Nicht-Steam-Spiele bekommen große Zufalls-IDs; Steam räumt deren Prefixe nie auf
                ref = {"launcher": "Steam", "title": "Nicht-Steam-Spiel", "detail": f"Shortcut {appid}"}
            else:
                ref = None  # Spiel deinstalliert, Prefix liegengeblieben
            yield str(pfx), ref, {"source": "steam", "appid": appid, "compatRoot": str(d)}


# ---------- Faugus ----------

def faugus():
    for base in (HOME / ".local/share/faugus-launcher", HOME / ".var/app/io.github.Faugus.faugus-launcher/data/faugus-launcher"):
        try:
            games = json.loads((base / "games.json").read_text())
        except (OSError, ValueError):
            continue
        for g in games:
            if g.get("prefix"):
                yield g["prefix"], {"launcher": "Faugus", "title": g.get("title") or g.get("gameid", "?"),
                                    "detail": g.get("runner") or ""}, {"faugusRunner": g.get("runner") or ""}


def faugus_default_runner() -> str:
    try:
        return json.loads((HOME / ".config/faugus-launcher/config.json").read_text()).get("default-runner", "")
    except (OSError, ValueError):
        return ""


# ---------- Lutris ----------

def _yaml_scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def _lutris_yml(path: Path) -> dict:
    """Minimal-Parser: nur game.prefix und wine.version, ohne PyYAML-Abhängigkeit."""
    out, top = {}, None
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        if line and not line[0].isspace():
            top = line.split(":", 1)[0]
            continue
        m = re.match(r"^  (\w+):\s*(.*)$", line)
        if m and top == "game" and m.group(1) == "prefix":
            out["prefix"] = _yaml_scalar(m.group(2))
        elif m and top == "wine" and m.group(1) == "version":
            out["wine"] = _yaml_scalar(m.group(2))
    return out


def lutris():
    db = HOME / ".local/share/lutris/pga.db"
    games_dir = HOME / ".local/share/lutris/games"
    if not db.is_file():
        return
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute("select name, configpath, directory, installed from games").fetchall()
        con.close()
    except sqlite3.Error:
        return
    for name, configpath, directory, installed in rows:
        cfg = _lutris_yml(games_dir / f"{configpath}.yml") if configpath else {}
        prefix = cfg.get("prefix") or directory
        if not prefix:
            continue
        extra = {"lutrisWine": cfg["wine"]} if cfg.get("wine") else {}
        yield prefix, {"launcher": "Lutris", "title": name, "detail": "" if installed else "nicht installiert"}, extra


# ---------- Heroic ----------

def heroic():
    for cfgdir in (HOME / ".config/heroic/GamesConfig", HOME / ".var/app/com.heroicgameslauncher.hgl/config/heroic/GamesConfig"):
        if not cfgdir.is_dir():
            continue
        for f in cfgdir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            for app, cfg in data.items():
                if isinstance(cfg, dict) and cfg.get("winePrefix"):
                    ver = (cfg.get("wineVersion") or {}).get("name", "")
                    yield cfg["winePrefix"], {"launcher": "Heroic", "title": app, "detail": ver}, {}


# ---------- Bottles ----------

def bottles():
    for base in (HOME / ".local/share/bottles/bottles", HOME / ".var/app/com.usebottles.bottles/data/bottles/bottles"):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            title = d.name
            try:
                m = re.search(r"^Name:\s*(.+)$", (d / "bottle.yml").read_text(errors="replace"), re.M)
                if m:
                    title = _yaml_scalar(m.group(1))
            except OSError:
                pass
            yield str(d), {"launcher": "Bottles", "title": title, "detail": ""}, {"source": "bottles"}


ALL = (steam, faugus, lutris, heroic, bottles)
