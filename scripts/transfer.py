"""Temporary LAN artifact delivery and bounded report collection; no remote execution."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import secrets

parser = argparse.ArgumentParser()
parser.add_argument("--bind", default="192.168.1.153")
parser.add_argument("--port", type=int, default=8786)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1] / "artifacts" / "transfer"
root.mkdir(parents=True, exist_ok=True)
token = secrets.token_urlsafe(24)


class Handler(BaseHTTPRequestHandler):
    def path_name(self):
        parts = self.path.split("/")
        if len(parts) != 3 or not secrets.compare_digest(parts[1], token):
            return None
        return parts[2] if re.fullmatch(r"[A-Za-z0-9_.-]+", parts[2]) else None

    def do_GET(self):
        name = self.path_name()
        path = root / (name or "")
        if not name or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        name = self.path_name()
        length = int(self.headers.get("Content-Length", "0"))
        if not name or not name.startswith("pi-") or not 0 < length <= 8 * 1024 * 1024:
            self.send_error(400)
            return
        (root / name).write_bytes(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"received\n")

    def log_message(self, fmt, *values):
        # Keep the transfer capability out of access logs.
        print(f"{self.command} {self.path.rsplit('/', 1)[-1]}", flush=True)


print(f"http://{args.bind}:{args.port}/{token}", flush=True)
ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()
