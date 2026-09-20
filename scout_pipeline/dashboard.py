"""A&R dashboard. Run `python dashboard.py`, then open http://127.0.0.1:8000

Serves dashboard.html plus a small JSON API over the scan database. Local only.
"""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import db

PORT = 8000
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

run_state = {"running": False, "demo": False, "started": None, "exit": None, "log": []}
run_lock = threading.Lock()


def load_tracks(include_demo: bool) -> list[dict]:
    conn = db.connect()
    where = "" if include_demo else "WHERE url NOT LIKE '%/demo/%'"
    rows = conn.execute(
        f"SELECT url, title, artist, verdict, evidence, scanned_at, details FROM tracks {where}"
    ).fetchall()
    out = []
    for url, title, artist, verdict, evidence, scanned_at, details in rows:
        ev = json.loads(evidence or "{}")
        d = json.loads(details or "{}")
        timeline = ev.get("risk_timeline") or []
        out.append(
            {
                "url": url,
                "title": title,
                "artist": artist,
                "verdict": verdict,
                "scanned_at": scanned_at,
                "uploaded_at": d.get("uploaded_at"),
                "followers": d.get("followers"),
                "genre": d.get("genre"),
                "score": d.get("score"),
                "momentum": d.get("momentum"),
                "bot_risk": d.get("bot_risk"),
                "flags": d.get("flags") or [],
                "metrics": d.get("metrics") or {},
                "report": d.get("report"),
                "demo": "/demo/" in url,
                "evidence": {
                    "confidence": ev.get("confidence"),
                    "origin": ev.get("origin"),
                    "label": ev.get("industry_label"),
                    "label_status": ev.get("industry_label_status"),
                    "nearest": (ev.get("origin_map") or {}).get("summary_line"),
                    "peak_risk": max(timeline) if timeline else None,
                },
            }
        )
    # Best leads first; discarded AI tracks and rows without a score go last.
    out.sort(key=lambda t: (t["score"] is None, -(t["score"] or 0), -t["scanned_at"]))
    return out


def _run_scan(demo: bool) -> None:
    args = [sys.executable, "-u", "main.py"] + (["--demo"] if demo else [])
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.Popen(
            args, cwd=config.ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                run_state["log"].append(line[:300])
        proc.wait()
        run_state["exit"] = proc.returncode
    except Exception as exc:
        run_state["log"].append(f"Could not start scan: {exc}")
        run_state["exit"] = 1
    finally:
        run_state["running"] = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the terminal quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def do_GET(self):
        if not self._host_ok():
            return self._json({"error": "bad host"}, 403)
        path, _, query = self.path.partition("?")
        if path == "/":
            return self._send(200, (config.ROOT / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/tracks":
            return self._json({"tracks": load_tracks("demo=1" in query)})
        if path == "/api/status":
            return self._json({**run_state, "log": run_state["log"][-12:], "scan_budget": config.MAX_SCANS_PER_RUN})
        if path.startswith("/reports/"):
            name = path.rsplit("/", 1)[-1]
            file = config.REPORT_DIR / name
            if file.parent == config.REPORT_DIR and file.is_file() and name.endswith(".html"):
                return self._send(200, file.read_bytes(), "text/html; charset=utf-8")
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        # A live scan spends HumanStandard credits, so refuse anything that is not
        # our own page: a foreign site cannot set this header without a CORS preflight.
        if not self._host_ok() or self.headers.get("X-Requested-With") != "dashboard":
            return self._json({"error": "forbidden"}, 403)
        if self.path.split("?")[0] != "/api/run":
            return self._json({"error": "not found"}, 404)
        demo = "demo=1" in self.path
        with run_lock:
            if run_state["running"]:
                return self._json({"error": "a scan is already running"}, 409)
            run_state.update(running=True, demo=demo, started=time.time(), exit=None, log=[])
        threading.Thread(target=_run_scan, args=(demo,), daemon=True).start()
        return self._json({"started": True})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard running at http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
