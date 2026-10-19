"""Erzeugt cellarium/web/demo.json – frei erfundene Beispieldaten für die GitHub-Page-Demo."""

import hashlib
import json
import time
from pathlib import Path

H = "/home/alex"
NOW = time.time()
DAY = 86400
GB = 1_000_000_000


def P(name, version="", publisher="", runtime=False):
    return {"name": name, "version": version, "publisher": publisher, "location": "", "runtime": runtime}


RT = [P("Wine Mono Windows Support", "9.4.0", "Wine", True), P("Microsoft Visual C++ 2015-2022 Redistributable (x64)", "14.40.33810", "Microsoft Corporation", True)]
WEBVIEW = P("Microsoft Edge WebView2 Runtime", "141.0.3537.71", "Microsoft Corporation", True)

GE10 = f"{H}/.local/share/Steam/compatibilitytools.d/GE-Proton10-25"
GE11 = f"{H}/.local/share/Steam/compatibilitytools.d/GE-Proton11-7"
EXP = f"{H}/.local/share/Steam/steamapps/common/Proton - Experimental"
P9 = f"{H}/.local/share/Steam/steamapps/common/Proton 9.0 (Beta)"

prefixes = [
    dict(path=f"{H}/Games/ubisoft-connect", source="lutris", kind="proton", version="GE-Proton10-25", protonPath=GE10, size=96.4 * GB, used=2,
         refs=[("Lutris", "Ubisoft Connect", ""), ("Lutris", "Assassin's Creed Mirage", "")],
         programs=[P("Assassin's Creed Mirage", "1.0.7", "Ubisoft"), P("Ubisoft Connect", "164.0.0", "Ubisoft"), *RT], tricks=["d3dcompiler_43", "corefonts"]),
    dict(path=f"{H}/Games/battlenet", source="lutris", kind="proton", version="GE-Proton11-7", protonPath=GE11, size=68.2 * GB, used=0.02, running=7,
         refs=[("Lutris", "Battle.net", "")],
         programs=[P("Battle.net", "2.42.1", "Blizzard Entertainment"), P("Diablo IV", "", "Blizzard Entertainment"), P("World of Warcraft", "", "Blizzard Entertainment"), *RT, WEBVIEW]),
    dict(path=f"{H}/WinePrefixes/default", source="faugus", kind="proton", version="GE-Proton11-7", protonPath=f"{H}/.local/share/Steam/compatibilitytools.d/Proton-GE Latest", size=24.8 * GB, used=1,
         refs=[("Faugus", "Guild Wars 2", "Proton-GE Latest")],
         programs=[P("Guild Wars 2", "", "ArenaNet"), P("CHITUBOX", "2.3.1", "CBD-Tech"), *RT, WEBVIEW], tricks=["d3dx9_43"]),
    dict(path=f"{H}/WinePrefixes/default/launcher-test", source="umu", kind="proton", version="GE-Proton11-1", protonPath=GE11, size=1.2 * GB, used=74,
         refs=[], programs=[P("Guild Wars 2", "", "ArenaNet"), *RT]),
    dict(path=f"{H}/WinePrefixes/battlenet", source="faugus", kind="proton", version="GE-Proton11-7", protonPath=GE11, size=3.1 * GB, used=40,
         refs=[("Faugus", "Battle.net", "Proton-GE Latest")],
         programs=[P("Battle.net", "2.41.0", "Blizzard Entertainment"), P("Hearthstone", "", "Blizzard Entertainment"), *RT]),
    dict(path=f"{H}/.wine", source="wine", kind="wine", size=12.3 * GB, used=12, default=True,
         refs=[], programs=[P("Notepad++ (64-bit x64)", "8.7", "Notepad++ Team"), P("7-Zip 24.08 (x64)", "24.08", "Igor Pavlov"), P("Foobar2000", "2.1.6", "Peter Pawlowski"), *RT]),
    dict(path=f"{H}/.local/share/Steam/steamapps/compatdata/1245620/pfx", source="steam", kind="proton", version="9.0-203", protonPath=P9, size=0.41 * GB, used=5, appid="1245620",
         refs=[("Steam", "ELDEN RING", "AppID 1245620")], programs=[*RT]),
    dict(path=f"{H}/.local/share/Steam/steamapps/compatdata/1091500/pfx", source="steam", kind="proton", version="11.0-100", protonPath=EXP, size=0.52 * GB, used=9, appid="1091500",
         refs=[("Steam", "Cyberpunk 2077", "AppID 1091500")], programs=[P("REDprelauncher", "", "CD PROJEKT RED"), *RT]),
    dict(path=f"{H}/.local/share/Steam/steamapps/compatdata/377160/pfx", source="steam", kind="proton", version="8.0-5", protonPath="", size=0.38 * GB, used=410, appid="377160",
         refs=[], programs=[*RT]),
    dict(path=f"{H}/Games/epic-games-store", source="lutris", kind="proton", version="GE-Proton10-25", protonPath=GE10, size=1.4 * GB, used=120,
         refs=[("Lutris", "Epic Games Store", "")], programs=[P("Epic Games Launcher", "1.3.128", "Epic Games, Inc."), *RT], tricks=["corefonts"]),
    dict(path=f"{H}/Games/ea-app", source="lutris", kind="proton", version="GE-Proton10-25", protonPath=GE10, size=1.7 * GB, used=230,
         refs=[("Lutris", "EA App", "")], programs=[P("EA app", "13.402", "Electronic Arts"), *RT], tricks=["corefonts", "win10"]),
    dict(path=f"{H}/Games/Heroic/Prefixes/default/Hades", source="heroic", kind="proton", version="GE-Proton10-25", protonPath=GE10, size=0.65 * GB, used=18,
         refs=[("Heroic", "Hades", "GE-Proton10-25")], programs=[*RT]),
    dict(path=f"{H}/.local/share/bottles/bottles/Office", source="bottles", kind="wine", size=2.4 * GB, used=33,
         refs=[("Bottles", "Office", "")], programs=[P("Microsoft Office Professional Plus 2010", "14.0.7015", "Microsoft Corporation"), *RT]),
    dict(path=f"{H}/.wine-ahk", source="wine", kind="wine", size=0.84 * GB, used=95,
         refs=[], programs=[P("AutoHotkey 1.1.37.02", "1.1.37.02", "Lexikos")]),
    dict(path=f"{H}/Games/umu/umu-default", source="umu", kind="proton", version="GE-Proton10-25", protonPath=GE10, size=0.68 * GB, used=160,
         refs=[], programs=[*RT]),
    dict(path=f"{H}/projects/unitytest", source="wine", kind="wine", size=0.69 * GB, used=210,
         refs=[], programs=[P("Unity Hub 3.9.1", "3.9.1", "Unity Technologies Inc.")]),
]

out = []
ids = {}
for d in prefixes:
    pid = hashlib.sha1(d["path"].encode()).hexdigest()[:12]
    ids[d["path"]] = pid
    compat = None
    if d["kind"] == "proton":
        compat = d["path"][:-4] if d["path"].endswith("/pfx") else d["path"]
    out.append({
        "id": pid, "path": d["path"], "autoName": d["refs"][0][1] if d["refs"] else (f"Steam-App {d['appid']}" if d.get("appid") else d["path"].rsplit("/", 1)[1]),
        "source": d["source"], "refs": [{"launcher": a, "title": b, "detail": c} for a, b, c in d["refs"]],
        "arch": "win64", "programs": d["programs"], "winetricks": d.get("tricks", []),
        "lastUsed": NOW - d["used"] * DAY, "isDefault": d.get("default", False), "faugusRunner": "", "lutrisWine": "",
        "appid": d.get("appid"), "kind": d["kind"], "compatRoot": compat, "version": d.get("version", ""),
        "protonPath": d.get("protonPath", ""), "size": int(d["size"]), "nestedIn": None, "contains": [],
        "label": "", "notes": "", "hidden": False, "running": d.get("running", 0), "runnerOverride": "",
        "runner": f"proton:{d['protonPath']}" if d.get("protonPath") else ("wine:/usr/bin/wine" if d["kind"] == "wine" else None),
    })

by_path = {p["path"]: p for p in out}
for p in out:
    parent = p["path"].rsplit("/", 1)[0]
    if parent in by_path:
        p["nestedIn"] = by_path[parent]["id"]
        by_path[parent]["contains"].append(p["id"])
by_path[f"{H}/.wine-ahk"]["notes"] = "Nur für die AHK-Makros. Nicht löschen."

runners = [
    {"id": "wine:/usr/bin/wine", "kind": "wine", "path": "/usr/bin/wine", "label": "System: wine-11.20"},
    {"id": f"wine:{H}/.local/share/lutris/runners/wine/wine-ge-8-26-x86_64/bin/wine", "kind": "wine", "path": "", "label": "Lutris: wine-ge-8-26-x86_64"},
    {"id": f"proton:{GE10}", "kind": "proton", "path": GE10, "label": "GE-Proton10-25"},
    {"id": f"proton:{GE11}", "kind": "proton", "path": GE11, "label": "GE-Proton11-7"},
    {"id": f"proton:{H}/.local/share/Steam/compatibilitytools.d/Proton-GE Latest", "kind": "proton", "path": "", "label": "Proton-GE Latest (GE-Proton11-7)"},
    {"id": f"proton:{P9}", "kind": "proton", "path": P9, "label": "Proton 9.0 (Beta) (9.0-203)"},
    {"id": f"proton:{EXP}", "kind": "proton", "path": EXP, "label": "Proton - Experimental (11.0-100)"},
]

data = {"prefixes": out, "runners": runners, "scanning": False, "measuring": 0, "scannedAt": NOW,
        "version": "demo", "demo": True, "home": H, "umu": True}
target = Path(__file__).resolve().parent.parent / "cellarium/web/demo.json"
target.write_text(json.dumps(data, ensure_ascii=False, indent=1))
print(f"{target}: {len(out)} Prefixe")
