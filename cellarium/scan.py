"""Findet Prefixe, sammelt ihre Eckdaten und misst im Hintergrund die Größe."""

import hashlib
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config, launchers, registry

HOME = Path.home()
# Nicht hineinschauen: Prefix-Innereien, Caches und Steam (das kommt über die Bibliotheken)
SKIP = {"drive_c", "dosdevices", "pfx", "shadercache", "gstreamer-1.0", "node_modules", ".git",
        ".cache", "Trash", "__pycache__", "steamapps", ".npm", ".cargo", ".rustup", "go"}


def prefix_id(path: str) -> str:
    return hashlib.sha1(path.encode()).hexdigest()[:12]


def is_prefix(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "system.reg")) and os.path.isdir(os.path.join(path, "drive_c"))


def walk(root: str, depth: int, found: set, exclude: set) -> None:
    try:
        it = os.scandir(root)
    except OSError:
        return
    with it:
        for e in it:
            try:
                if not e.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if e.name in SKIP or e.name.startswith(".Trash") or e.path in exclude:
                continue
            if is_prefix(e.path):
                found.add(e.path)
            if depth > 1:
                walk(e.path, depth - 1, found, exclude)


def _proton_info(path: Path) -> dict:
    """Proton/umu legen config_info + version neben bzw. in den Prefix."""
    root = None
    if path.name == "pfx" and (path.parent / "config_info").is_file():
        root = path.parent
    elif (path / "config_info").is_file() or (path / "version").is_file():
        root = path
    if root is None:
        return {"kind": "wine", "compatRoot": None, "version": "", "protonPath": ""}
    version, proton_path = "", ""
    try:
        lines = (root / "config_info").read_text(errors="replace").splitlines()
        version = lines[0].strip() if lines else ""
        for line in lines[1:]:
            for marker in ("/files/", "/dist/"):
                if marker in line:
                    proton_path = line.split(marker, 1)[0]
                    break
            if proton_path:
                break
    except OSError:
        pass
    if not version:
        try:
            version = (root / "version").read_text().split()[-1]
        except (OSError, IndexError):
            pass
    return {"kind": "proton", "compatRoot": str(root), "version": version, "protonPath": proton_path}


def _display_name(path: Path, refs: list, appid=None) -> str:
    titles = [r["title"] for r in refs if r]
    if titles:
        return titles[0]
    if appid:
        return f"Steam-App {appid}"
    base = path.name
    if base in ("pfx", "wineprefix", "prefix"):
        return path.parent.name
    if base == "default":
        return f"{path.parent.name}/default"
    return base


def _guess_source(path: Path, refs: list, extra: dict) -> str:
    if extra.get("source"):
        return extra["source"]
    if refs:
        return refs[0]["launcher"].lower()
    if (path / "lutris.json").exists():
        return "lutris"
    if (path / ".faugus.lock").exists():
        return "faugus"
    if (path / "config_info").exists():
        return "umu"
    return "wine"


def describe(path: str, refs: list, extra: dict) -> dict:
    p = Path(path)
    proton = _proton_info(p)
    mtimes = []
    for f in ("user.reg", "system.reg", "userdef.reg"):
        try:
            mtimes.append((p / f).stat().st_mtime)
        except OSError:
            pass
    refs = [r for r in refs if r]
    return {
        "id": prefix_id(path),
        "path": path,
        "autoName": _display_name(p, refs, extra.get("appid")),
        "source": _guess_source(p, refs, extra),
        "refs": refs,
        "arch": registry.read_arch(p),
        "programs": registry.read_programs(p),
        "winetricks": registry.read_winetricks(p),
        "lastUsed": max(mtimes) if mtimes else None,
        "isDefault": path == str(HOME / ".wine"),
        "faugusRunner": extra.get("faugusRunner", ""),
        "lutrisWine": extra.get("lutrisWine", ""),
        "appid": extra.get("appid"),
        **proton,
    }


class SizeCache:
    FILE = config.CACHE_DIR / "sizes.json"

    def __init__(self):
        try:
            self.data = json.loads(self.FILE.read_text())
        except (OSError, ValueError):
            self.data = {}
        self.lock = threading.Lock()

    def get(self, path):
        v = self.data.get(path)
        return v[0] if v else None

    def put(self, path, size):
        with self.lock:
            self.data[path] = [size, time.time()]
            config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data))
            tmp.replace(self.FILE)


def measure(path: str) -> int | None:
    try:
        out = subprocess.run(["du", "-sb", path], capture_output=True, text=True, timeout=600).stdout
        return int(out.split()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


class Scanner:
    def __init__(self):
        self.lock = threading.Lock()
        self.prefixes: dict[str, dict] = {}
        self.scanning = False
        self.measuring: set[str] = set()
        self.scanned_at = None
        self.sizes = SizeCache()
        self.pool = ThreadPoolExecutor(max_workers=3)

    def rescan_async(self):
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        try:
            cfg = config.load()
            refs: dict[str, list] = {}
            extras: dict[str, dict] = {}
            for source in launchers.ALL:
                try:
                    for path, ref, extra in source():
                        real = os.path.realpath(os.path.expanduser(path))
                        if not is_prefix(real):
                            continue
                        refs.setdefault(real, []).append(ref)
                        extras.setdefault(real, {}).update(extra)
                except Exception as exc:  # ein kaputter Launcher soll den Rest nicht verhindern
                    print(f"cellarium: {source.__name__}: {exc}")

            found: set[str] = set()
            exclude = {os.path.realpath(os.path.expanduser(x)) for x in cfg["exclude"]}
            for root in cfg["roots"]:
                root = os.path.realpath(os.path.expanduser(root))
                if is_prefix(root):
                    found.add(root)
                walk(root, int(cfg["maxDepth"]), found, exclude)
            found = {os.path.realpath(p) for p in found} | set(refs)
            found -= exclude

            result = {}
            with ThreadPoolExecutor(max_workers=6) as ex:
                for info in ex.map(lambda p: describe(p, refs.get(p, []), extras.get(p, {})), sorted(found)):
                    info["size"] = self.sizes.get(info["path"])
                    result[info["id"]] = info

            paths = {i["path"]: i["id"] for i in result.values()}
            for info in result.values():
                parent = os.path.dirname(info["path"])
                info["nestedIn"] = None
                info["contains"] = []
                while parent not in ("/", ""):
                    if parent in paths:
                        info["nestedIn"] = paths[parent]
                        break
                    parent = os.path.dirname(parent)
            for info in result.values():
                if info["nestedIn"]:
                    result[info["nestedIn"]]["contains"].append(info["id"])

            with self.lock:
                self.prefixes = result
                self.scanned_at = time.time()
            for info in result.values():
                self.measure_async(info["id"])
        finally:
            with self.lock:
                self.scanning = False

    def measure_async(self, pid):
        with self.lock:
            info = self.prefixes.get(pid)
            if not info or pid in self.measuring:
                return
            self.measuring.add(pid)
            path = info["path"]

        def job():
            size = measure(path)
            with self.lock:
                self.measuring.discard(pid)
                if size is not None and pid in self.prefixes:
                    self.prefixes[pid]["size"] = size
            if size is not None:
                self.sizes.put(path, size)

        self.pool.submit(job)

    def forget(self, pid):
        with self.lock:
            info = self.prefixes.pop(pid, None)
        return info

    def get(self, pid):
        with self.lock:
            return self.prefixes.get(pid)

    def snapshot(self):
        with self.lock:
            return {
                "prefixes": list(self.prefixes.values()),
                "scanning": self.scanning,
                "measuring": len(self.measuring),
                "scannedAt": self.scanned_at,
            }


def _wineish(pid: str) -> bool:
    """Nur Wine-Prozesse zählen – nicht etwa eine Shell, in der jemand WINEPREFIX exportiert hat."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            cmd = fh.read().lower()
    except OSError:
        return False
    return any(k in cmd for k in (b".exe", b"wine", b"proton", b"umu", b"pressure-vessel"))


def running_prefixes() -> dict[str, list[int]]:
    """Realpfad des Prefixes -> PIDs, ermittelt über /proc/*/environ."""
    pids: dict[str, list[int]] = {}
    uid = os.getuid()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            with open(f"/proc/{pid}/environ", "rb") as fh:
                env = fh.read().split(b"\0")
        except OSError:
            continue
        found = None
        for item in env:
            if item.startswith(b"WINEPREFIX="):
                found = item[11:].decode(errors="replace")
                break
            if item.startswith(b"STEAM_COMPAT_DATA_PATH=") and found is None:
                found = item[23:].decode(errors="replace").rstrip("/") + "/pfx"
        if found and _wineish(pid):
            pids.setdefault(os.path.realpath(found), []).append(int(pid))
    return pids
