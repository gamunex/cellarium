"""Liest installierte Programme aus Wines Registry-Dateien (system.reg / user.reg).

Wine schreibt die Registry als Text („WINE REGISTRY Version 2“). Uns interessieren nur die
Uninstall-Schlüssel – das ist dieselbe Liste, die Windows unter „Apps & Features“ zeigt.
"""

import re
from pathlib import Path

_SECTION = re.compile(
    r"^\[Software\\\\(?:Wow6432Node\\\\)?Microsoft\\\\Windows\\\\CurrentVersion\\\\Uninstall\\\\(.+?)\]",
    re.IGNORECASE,
)
_VALUE = re.compile(r'^"((?:[^"\\]|\\.)*)"=(?:str\(\d\):)?"((?:[^"\\]|\\.)*)"')
_DWORD = re.compile(r'^"((?:[^"\\]|\\.)*)"=dword:([0-9a-fA-F]{8})')

# Laufzeitbibliotheken, die in fast jedem Prefix stecken und die Programmliste nur verstopfen
RUNTIME = re.compile(
    r"wine (mono|gecko)|visual c\+\+|vcredist|directx|\.net (framework|runtime|desktop)|"
    r"desktop runtime|asp\.net core|webview2|microsoft edge|xna framework|physx|openal|vulkan run ?time|windows sdk|"
    r"ue4 prerequisites|easyanticheat|battleye|microsoft update health",
    re.IGNORECASE,
)


def unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c != "\\" or i + 1 >= len(s):
            out.append(c)
            i += 1
            continue
        n = s[i + 1]
        if n == "x":
            j = i + 2
            while j < len(s) and j < i + 6 and s[j] in "0123456789abcdefABCDEF":
                j += 1
            if j > i + 2:
                out.append(chr(int(s[i + 2:j], 16)))
                i = j
                continue
        out.append({"n": "\n", "t": "\t", "r": "\r", "0": ""}.get(n, n))
        i += 2
    return "".join(out)


def read_programs(prefix: Path) -> list[dict]:
    entries: dict[str, dict] = {}
    for name in ("system.reg", "user.reg"):
        try:
            fh = open(prefix / name, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            current = None
            for line in fh:
                if line.startswith("["):
                    m = _SECTION.match(line)
                    current = entries.setdefault(m.group(1).lower(), {}) if m else None
                    continue
                if current is None or not line.startswith('"'):
                    continue
                m = _VALUE.match(line)
                if m:
                    current[unescape(m.group(1))] = unescape(m.group(2))
                    continue
                m = _DWORD.match(line)
                if m:
                    current[unescape(m.group(1))] = int(m.group(2), 16)

    programs = {}
    for e in entries.values():
        name = (e.get("DisplayName") or "").strip()
        if not name or e.get("SystemComponent") == 1 or e.get("ParentKeyName"):
            continue
        key = name.lower()
        if key in programs:
            continue
        programs[key] = {
            "name": name,
            "version": (e.get("DisplayVersion") or "").strip(),
            "publisher": (e.get("Publisher") or "").strip(),
            "location": (e.get("InstallLocation") or "").strip(),
            "runtime": bool(RUNTIME.search(name)),
        }
    return sorted(programs.values(), key=lambda p: (p["runtime"], p["name"].lower()))


def read_winetricks(prefix: Path) -> list[str]:
    verbs: list[str] = []
    for name in ("winetricks.log", "winetricks.log.forced"):
        try:
            text = (prefix / name).read_text(errors="replace")
        except OSError:
            continue
        for v in text.split():
            if v.startswith("-") or v in ("list-installed", "list", "apps", "dlls", "fonts", "settings", "gui") or v in verbs:
                continue
            verbs.append(v)
    return verbs


def read_arch(prefix: Path) -> str:
    try:
        with open(prefix / "system.reg", encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(8), fh):
                if line.startswith("#arch="):
                    return line.strip()[6:]
    except OSError:
        pass
    return ""
