"""Kleiner HTTP-Server: liefert die Oberfläche aus und nimmt Aktionen entgegen.

Er hört nur auf 127.0.0.1. Jede API-Anfrage braucht das Token, das beim Start erzeugt und dem
Fenster im URL-Fragment mitgegeben wird – sonst könnte jede Webseite im Browser per fetch() auf
localhost Befehle auslösen.
"""

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, config, runners, scan

WEB = Path(__file__).with_name("web")
LOG_DIR = config.CACHE_DIR / "logs"
TOOLS = {"winecfg", "regedit", "uninstaller", "winetricks", "run", "kill", "open", "trash"}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class App:
    def __init__(self, token: str, idle_exit: bool):
        self.token = token
        self.idle_exit = idle_exit
        self.last_ping = time.time()
        self.scanner = scan.Scanner()
        self.runners = runners.list_runners()
        self.scanner.rescan_async()

    # ---------- Zustand ----------

    def state(self):
        snap = self.scanner.snapshot()
        running = scan.running_prefixes()
        meta = config.load()["meta"]
        for p in snap["prefixes"]:
            m = meta.get(p["path"], {})
            p["label"] = m.get("label", "")
            p["notes"] = m.get("notes", "")
            p["hidden"] = bool(m.get("hidden"))
            p["running"] = len(running.get(os.path.realpath(p["path"]), []))
            r = runners.resolve(p, self.runners)
            p["runner"] = r["id"] if r else None
            p["runnerOverride"] = m.get("runner", "")
        return {**snap, "runners": self.runners, "version": __version__, "demo": False,
                "home": str(Path.home()), "umu": bool(runners.umu_binary())}

    def _prefix(self, pid):
        info = self.scanner.get(pid)
        if not info:
            raise ApiError(HTTPStatus.NOT_FOUND, "Prefix nicht gefunden – bitte neu scannen.")
        return info

    # ---------- Aktionen ----------

    def meta(self, pid, body):
        info = self._prefix(pid)
        allowed = {k: body[k] for k in ("label", "notes", "hidden", "runner") if k in body}
        if "runner" in allowed and allowed["runner"] and allowed["runner"] not in {r["id"] for r in self.runners}:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Unbekannter Runner.")
        return {"meta": config.update_meta(info["path"], allowed)}

    def action(self, pid, body):
        info = self._prefix(pid)
        tool = body.get("action")
        if tool not in TOOLS:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Unbekannte Aktion.")

        if tool == "open":
            target = Path(info["path"], "drive_c")
            self._spawn(["xdg-open", str(target if target.is_dir() else info["path"])], dict(os.environ), pid)
            return {"message": "Ordner geöffnet."}
        if tool == "trash":
            return self._trash(info, body)
        if tool == "kill":
            return self._kill(info)

        runner = runners.resolve(info, self.runners)
        if runner is None:
            raise ApiError(HTTPStatus.CONFLICT, "Kein passender Runner gefunden – bitte im Detail einen wählen.")

        args = []
        if tool == "run":
            exe = self._pick_exe(info)
            if not exe:
                return {"message": "Abgebrochen."}
            args = [exe]
        if tool == "winetricks" and runner["kind"] == "wine" and not shutil.which("winetricks"):
            raise ApiError(HTTPStatus.CONFLICT, "winetricks ist nicht installiert.")

        cmd, env = runners.command(info, runner, tool, args)
        self._spawn(cmd, env, pid, cwd=os.path.dirname(args[0]) if args else None)
        names = {"winecfg": "winecfg", "regedit": "Registry-Editor", "uninstaller": "Deinstallation",
                 "winetricks": "winetricks", "run": Path(args[0]).name if args else ""}
        return {"message": f"{names[tool]} startet ({runner['label']})."}

    def _kill(self, info):
        # Per Signal statt wineserver -k: das klappt auch, wenn der Server von einer anderen Wine-Version stammt
        pids = scan.running_prefixes().get(os.path.realpath(info["path"]), [])
        if not pids:
            return {"message": "Im Prefix läuft nichts."}
        for p in pids:
            try:
                os.kill(p, signal.SIGTERM)
            except OSError:
                pass

        def finish():
            time.sleep(4)
            for p in scan.running_prefixes().get(os.path.realpath(info["path"]), []):
                try:
                    os.kill(p, signal.SIGKILL)
                except OSError:
                    pass
        threading.Thread(target=finish, daemon=True).start()
        return {"message": f"{len(pids)} Prozess{'e' if len(pids) > 1 else ''} beendet."}

    def _spawn(self, cmd, env, pid, cwd=None):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(LOG_DIR / f"{pid}.log", "ab")
        log.write(f"\n=== {time.strftime('%F %T')} {' '.join(cmd)}\n".encode())
        log.flush()
        try:
            subprocess.Popen(cmd, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, f"Start fehlgeschlagen: {exc}")
        finally:
            log.close()

    def _pick_exe(self, info):
        start = Path(info["path"], "drive_c")
        start = str(start if start.is_dir() else info["path"]) + "/"
        if shutil.which("kdialog"):
            cmd = ["kdialog", "--title", "Programm im Prefix starten", "--getopenfilename", start,
                   "Windows-Programme (*.exe *.msi *.EXE *.MSI)"]
        elif shutil.which("zenity"):
            cmd = ["zenity", "--file-selection", "--title=Programm im Prefix starten", f"--filename={start}",
                   "--file-filter=Windows-Programme | *.exe *.msi *.EXE *.MSI"]
        else:
            raise ApiError(HTTPStatus.CONFLICT, "Weder kdialog noch zenity gefunden.")
        out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
        return out if out and os.path.isfile(out) else None

    def _trash(self, info, body):
        if body.get("confirm") != info["path"]:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Bestätigung fehlt.")
        if scan.running_prefixes().get(os.path.realpath(info["path"])):
            raise ApiError(HTTPStatus.CONFLICT, "Im Prefix laufen noch Programme – erst beenden.")
        # Bei Steam/umu gehört der Ordner mit config_info/version dazu
        target = Path(info.get("compatRoot") or info["path"])
        home = Path.home().resolve()
        if target.resolve() in (home, Path("/")) or len(target.resolve().parts) < 3:
            raise ApiError(HTTPStatus.FORBIDDEN, "Diesen Ordner verschiebe ich nicht.")
        for tool in (["gio", "trash", str(target)], ["kioclient", "move", str(target), "trash:/"]):
            if shutil.which(tool[0]):
                res = subprocess.run(tool, capture_output=True, text=True)
                if res.returncode == 0 and not target.exists():
                    self.scanner.forget(info["id"])
                    config.drop_meta(info["path"])
                    return {"message": f"„{target.name}“ liegt jetzt im Papierkorb."}
                err = res.stderr.strip()
                raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, f"Papierkorb fehlgeschlagen: {err or 'unbekannt'}")
        raise ApiError(HTTPStatus.CONFLICT, "Weder gio noch kioclient gefunden.")


class Handler(SimpleHTTPRequestHandler):
    app: App = None
    port: int = 0

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _host_ok(self):
        # Schutz gegen DNS-Rebinding: nur Anfragen, die wirklich an 127.0.0.1/localhost gehen
        return self.headers.get("Host", "") in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def _json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api(self, method):
        if not self._host_ok() or self.headers.get("X-Cellarium-Token") != self.app.token:
            return self._json(HTTPStatus.FORBIDDEN, {"error": "Kein Zugriff."})
        parts = self.path.split("?", 1)[0].strip("/").split("/")[1:]
        body = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except ValueError:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "Ungültiges JSON."})
        try:
            self.app.last_ping = time.time()
            match (method, parts):
                case ("GET", ["state"]):
                    return self._json(HTTPStatus.OK, self.app.state())
                case ("GET", ["ping"]):
                    return self._json(HTTPStatus.OK, {"ok": True})
                case ("POST", ["rescan"]):
                    self.app.runners = runners.list_runners()
                    self.app.scanner.rescan_async()
                    return self._json(HTTPStatus.OK, {"ok": True})
                case ("POST", ["prefix", pid, "meta"]):
                    return self._json(HTTPStatus.OK, self.app.meta(pid, body))
                case ("POST", ["prefix", pid, "action"]):
                    return self._json(HTTPStatus.OK, self.app.action(pid, body))
            return self._json(HTTPStatus.NOT_FOUND, {"error": "Unbekannter Endpunkt."})
        except ApiError as exc:
            return self._json(exc.status, {"error": str(exc)})

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        if not self._host_ok():
            return self.send_error(HTTPStatus.FORBIDDEN)
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        self.send_error(HTTPStatus.NOT_FOUND)


def serve(port: int, token: str, idle_exit: bool, on_ready=None):
    app = App(token, idle_exit)
    Handler.app = app
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    Handler.port = httpd.server_address[1]

    if idle_exit:
        def watchdog():
            # Fenster zu → keine Pings mehr → Server beendet sich nach einer Minute
            while True:
                time.sleep(10)
                if time.time() - app.last_ping > 60:
                    httpd.shutdown()
                    return
        threading.Thread(target=watchdog, daemon=True).start()

    if on_ready:
        on_ready(Handler.port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
