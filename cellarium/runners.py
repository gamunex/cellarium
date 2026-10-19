"""Welches Wine/Proton gehört zu einem Prefix, und wie startet man Werkzeuge darin.

Wichtig: Ein Proton-Prefix nie mit System-Wine öffnen (und umgekehrt) – Wine würde den Prefix
sofort auf seine eigene Version „aktualisieren“. Deshalb läuft alles über den Runner, der den
Prefix angelegt hat, solange der Nutzer keinen anderen wählt.
"""

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from . import config, launchers

HOME = Path.home()


@lru_cache(maxsize=None)
def _wine_version(binary: str) -> str:
    try:
        return subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _proton_label(d: Path) -> str:
    try:
        ver = (d / "version").read_text().split()[-1]
    except (OSError, IndexError):
        ver = ""
    return f"{d.name} ({ver})" if ver and ver not in d.name else d.name


def list_runners() -> list[dict]:
    runners = []
    seen = set()

    def add(r):
        key = os.path.realpath(r["path"])
        if key not in seen:
            seen.add(key)
            runners.append(r)

    for binary in filter(None, (shutil.which("wine"), "/opt/wine-cachyos/bin/wine")):
        if os.path.isfile(binary):
            add({"id": f"wine:{binary}", "kind": "wine", "path": binary,
                 "label": f"System: {_wine_version(binary) or binary}"})
    for d in sorted((HOME / ".local/share/lutris/runners/wine").glob("*/bin/wine")):
        add({"id": f"wine:{d}", "kind": "wine", "path": str(d), "label": f"Lutris: {d.parent.parent.name}"})

    proton_dirs = []
    for root in launchers.steam_roots():
        proton_dirs += sorted((root / "compatibilitytools.d").glob("*"))
    for lib in launchers.steam_libraries():
        proton_dirs += sorted((lib / "steamapps/common").glob("Proton*"))
    proton_dirs += sorted((HOME / ".local/share/umu/compatibilitytools").glob("*"))
    for d in proton_dirs:
        if (d / "proton").is_file():
            add({"id": f"proton:{d}", "kind": "proton", "path": str(d), "label": _proton_label(d)})
    return runners


def umu_binary() -> str | None:
    for c in (shutil.which("umu-run"), HOME / ".local/share/faugus-launcher/umu-run",
              HOME / ".local/share/lutris/runtime/umu/umu-run"):
        if c and os.access(c, os.X_OK):
            return str(c)
    return None


def resolve(info: dict, runners: list[dict]) -> dict | None:
    """Gewählter Runner > Runner, der den Prefix angelegt hat > passender Launcher-Runner > System-Wine."""
    by_id = {r["id"]: r for r in runners}
    override = config.load()["meta"].get(info["path"], {}).get("runner")
    if override in by_id:
        return by_id[override]

    if info["kind"] == "proton":
        if info.get("protonPath"):
            r = by_id.get(f"proton:{info['protonPath']}")
            if r:
                return r
        for r in runners:
            if r["kind"] == "proton" and info.get("version") and (
                    Path(r["path"]).name == info["version"] or Path(r["path"]).name == f"{info['version']}-x86_64"):
                return r
        for name in filter(None, (info.get("faugusRunner"), launchers.faugus_default_runner(), "Proton-GE Latest")):
            for r in runners:
                if r["kind"] == "proton" and Path(r["path"]).name == name:
                    return r
        return None  # lieber nichts tun als einen Proton-Prefix mit Wine anfassen

    if info.get("lutrisWine"):
        for r in runners:
            if r["kind"] == "wine" and info["lutrisWine"] in r["path"]:
                return r
    return next((r for r in runners if r["kind"] == "wine"), None)


def _proton_bin(proton_dir: str, name: str) -> str:
    for sub in ("files", "dist"):
        p = Path(proton_dir, sub, "bin", name)
        if p.is_file():
            return str(p)
    return name


def command(info: dict, runner: dict, tool: str, args: list[str] | None = None) -> tuple[list[str], dict]:
    """Baut Befehl + Umgebung für tool ∈ {winecfg, regedit, uninstaller, winetricks, run}."""
    args = args or []
    env = dict(os.environ)
    prefix = info["path"]
    env["WINEPREFIX"] = prefix
    env.pop("WINEARCH", None)

    if runner["kind"] == "wine":
        wine = runner["path"]
        if tool == "winetricks":
            env["WINE"] = wine
            env["WINESERVER"] = str(Path(wine).with_name("wineserver"))
            return ["winetricks", "--gui"], env
        if tool == "run":
            exe = args[0]
            if exe.lower().endswith(".msi"):
                return [wine, "msiexec", "/i", exe], env
            return [wine, exe], env
        return [wine, tool], env

    proton = runner["path"]
    compat = info.get("compatRoot") or prefix

    umu = umu_binary()
    if umu:
        # umu erwartet als WINEPREFIX das Verzeichnis, in dem pfx/ liegt (bei Steam compatdata/<id>)
        env.update({"WINEPREFIX": compat, "PROTONPATH": proton, "GAMEID": "umu-default",
                    "UMU_RUNTIME_UPDATE": "0"})
        base = [umu]
    else:
        steam_root = launchers.steam_roots()
        env.update({"STEAM_COMPAT_DATA_PATH": compat,
                    "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(steam_root[0] if steam_root else HOME / ".steam/steam")})
        base = [os.path.join(proton, "proton"), "run"]

    if tool == "winetricks":
        if umu:
            return base + ["winetricks", "--gui"], env
        env["WINE"] = _proton_bin(proton, "wine")
        env["WINESERVER"] = _proton_bin(proton, "wineserver")
        env["WINEPREFIX"] = prefix
        return ["winetricks", "--gui"], env
    if tool == "run":
        exe = args[0]
        if exe.lower().endswith(".msi"):
            return base + ["msiexec", "/i", exe], env
        return base + [exe], env
    return base + [tool], env
