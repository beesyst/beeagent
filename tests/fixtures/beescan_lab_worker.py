import http.server
import json
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import cast

root = Path(sys.argv[1])
subprocess.run(["/usr/sbin/ip", "link", "set", "lo", "up"], check=True)
rules = """table inet beescan {
 chain output {
 type filter hook output priority -150; policy drop;
 ip daddr 127.0.0.1 tcp dport 18080 accept
 ct state established tcp flags & (syn | ack) != syn accept
 }
}
"""
subprocess.run(["/usr/sbin/nft", "-f", "-"], input=rules, text=True, check=True)
counts = {18080: 0, 18081: 0}
requests = []
lock = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            server = cast(http.server.ThreadingHTTPServer, self.server)
            counts[server.server_port] += 1
            (root / "counts.json").write_text(json.dumps(counts))
            requests.append(
                {"port": server.server_port, "method": "GET", "path": self.path}
            )
            (root / "requests.json").write_text(json.dumps(requests))
        mode = (root / "mode").read_text().strip()
        if mode == "timeout":
            time.sleep(10)
        self.send_response(302 if mode == "redirect" else 200)
        self.send_header(
            "X-Beescan-Marker",
            "invalid"
            if mode == "malformed"
            else "absent"
            if mode == "negative" or mode.startswith("signal-")
            else "present",
        )
        self.send_header("Set-Cookie", "lab-secret=must-not-persist")
        if mode in {
            "signal-effective",
            "signal-hsts-missing",
            "signal-hsts-disabled",
            "signal-duplicate",
        }:
            self.send_header("X-Content-Type-Options", "nosniff")
        if mode == "signal-ineffective":
            self.send_header("X-Content-Type-Options", "invalid")
        if mode in {"signal-effective", "signal-ineffective", "ok"}:
            self.send_header(
                "Strict-Transport-Security", "max-age=60; includeSubDomains"
            )
        if mode == "signal-hsts-disabled":
            self.send_header("Strict-Transport-Security", "max-age=0")
        if mode == "signal-duplicate":
            self.send_header("X-Content-Type-Options", "nosniff")
        if mode == "signal-malformed":
            self.send_header("Strict-Transport-Security", "max-age=no")
        if mode == "redirect":
            self.send_header("Location", "http://127.0.0.1:18081/")
        if mode == "oversized":
            self.send_header("X-Oversized", "x" * 9000)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        with lock:
            server = cast(http.server.ThreadingHTTPServer, self.server)
            counts[server.server_port] += 1
            (root / "counts.json").write_text(json.dumps(counts))
            requests.append(
                {"port": server.server_port, "method": "HEAD", "path": self.path}
            )
            (root / "requests.json").write_text(json.dumps(requests))
        mode = (root / "mode").read_text().strip()
        if mode == "timeout":
            time.sleep(10)
        self.send_response(302 if mode == "redirect" else 200)
        self.send_header(
            "Content-Type",
            "invalid" if mode == "malformed" else "text/html; charset=utf-8",
        )
        self.send_header("Set-Cookie", "lab-secret=must-not-persist")
        if mode in {
            "signal-effective",
            "signal-hsts-missing",
            "signal-hsts-disabled",
            "signal-duplicate",
        }:
            self.send_header("X-Content-Type-Options", "nosniff")
        if mode == "signal-ineffective":
            self.send_header("X-Content-Type-Options", "invalid")
        if mode in {"signal-effective", "signal-ineffective", "ok"}:
            self.send_header(
                "Strict-Transport-Security", "max-age=60; includeSubDomains"
            )
        if mode == "signal-hsts-disabled":
            self.send_header("Strict-Transport-Security", "max-age=0")
        if mode == "signal-duplicate":
            self.send_header("X-Content-Type-Options", "nosniff")
        if mode == "signal-malformed":
            self.send_header("Strict-Transport-Security", "max-age=no")
        if mode == "redirect":
            self.send_header("Location", "http://127.0.0.1:18081/")
        if mode == "oversized":
            self.send_header("Location", "http://127.0.0.1:18081/" + "x" * 5000)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


for port in counts:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    if (root / "server.pem").exists():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / "server.pem", root / "server.key")
        server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
(root / "counts.json").write_text(json.dumps(counts))
(root / "requests.json").write_text(json.dumps(requests))
(root / "ready").write_text("ready")
while True:
    time.sleep(1)
