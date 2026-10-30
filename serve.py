"""
serve.py  -  Starts the dashboard on your own computer.

    python3.15 serve.py          then open   http://localhost:8000
Stop it with Ctrl + C.
"""
import json
import os
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from dash_api import catalog, run_case, CASES
from llm_diagnose import ai_available

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/cases":
            return self._send(200, json.dumps(catalog()), "application/json")
        if u.path == "/api/info":
            return self._send(200, json.dumps({"ai": ai_available()}), "application/json")
        if u.path == "/api/run":
            q = parse_qs(u.query)
            key = q.get("case", ["d1"])[0]
            agent = q.get("agent", ["revive"])[0]
            seed = int(q.get("seed", [random.randrange(1000)])[0])
            if key not in CASES or agent not in ("revive", "naive"):
                return self._send(400, json.dumps({"error": "bad request"}), "application/json")
            return self._send(200, json.dumps(run_case(key, agent, seed)), "application/json")
        self._send(404, "not found", "text/plain")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = 8000
    print(f"ReVive dashboard running.  Open  http://localhost:{port}  in your browser.  (Ctrl + C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
