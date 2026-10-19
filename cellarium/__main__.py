"""Startet Cellarium: Server im Hintergrund, Oberfläche als App-Fenster.

Läuft schon eine Instanz, wird nur ein neues Fenster dazu geöffnet.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import urllib.request

from . import __version__, config, server

INSTANCE = config.CACHE_DIR / "instance.json"
DEFAULT_PORT = 47110
BROWSERS = ("brave", "brave-browser", "chromium", "google-chrome-stable", "google-chrome", "vivaldi-stable",
            "microsoft-edge-stable")


def open_window(url: str, browser: str | None) -> None:
    candidates = [browser] if browser else [os.environ.get("CELLARIUM_BROWSER"), *BROWSERS]
    for name in filter(None, candidates):
        exe = shutil.which(name)
        if exe:
            # Chromium-Browser können eine Seite als eigenes Fenster ohne Tabs/Adressleiste zeigen
            cmd = [exe, f"--app={url}", "--class=cellarium"] if name != "firefox" else [exe, "--new-window", url]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def running_instance() -> str | None:
    try:
        inst = json.loads(INSTANCE.read_text())
        req = urllib.request.Request(f"http://127.0.0.1:{inst['port']}/api/ping",
                                     headers={"X-Cellarium-Token": inst["token"]})
        with urllib.request.urlopen(req, timeout=1) as res:
            if res.status == 200:
                return f"http://127.0.0.1:{inst['port']}/#t={inst['token']}"
    except (OSError, ValueError, KeyError):
        pass
    return None


def main() -> None:
    ap = argparse.ArgumentParser(prog="cellarium", description="Überblick über alle Wine- und Proton-Prefixe.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port auf 127.0.0.1 (Standard {DEFAULT_PORT}, 0 = beliebig)")
    ap.add_argument("--no-window", action="store_true", help="kein Fenster öffnen, nur die Adresse ausgeben")
    ap.add_argument("--browser", help="Browser für das App-Fenster (Standard: erster gefundener Chromium-Browser)")
    ap.add_argument("--stay", action="store_true", help="weiterlaufen, auch wenn kein Fenster mehr offen ist")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args()

    url = running_instance()
    if url:
        print(url)
        if not args.no_window:
            open_window(url, args.browser)
        return

    token = secrets.token_urlsafe(24)

    def ready(port):
        url = f"http://127.0.0.1:{port}/#t={token}"
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        INSTANCE.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid()}))
        os.chmod(INSTANCE, 0o600)
        print(f"Cellarium läuft: {url}", flush=True)
        if not args.no_window:
            open_window(url, args.browser)

    try:
        server.serve(args.port, token, idle_exit=not (args.stay or args.no_window), on_ready=ready)
    except OSError as exc:
        if args.port and exc.errno == 98:  # Port belegt → beliebigen nehmen
            server.serve(0, token, idle_exit=not (args.stay or args.no_window), on_ready=ready)
        else:
            raise
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if json.loads(INSTANCE.read_text()).get("token") == token:
                INSTANCE.unlink()
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    sys.exit(main())
