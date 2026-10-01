"""Fail-closed HTTP CONNECT proxy for the one active Logins site."""
from __future__ import annotations

import os
from pathlib import Path
import re
import select
import socket
import socketserver
from logins_policy import denied

ACTIVE = Path(os.environ.get("KIT_LOGINS_ACTIVE", "/var/lib/hermes-kit/logins-active-domain"))
HOST = re.compile(r"^[a-z0-9][a-z0-9.-]{1,251}[a-z0-9]$")


def permitted(host: str, active: str) -> bool:
    host = host.lower().rstrip(".")
    return bool(HOST.fullmatch(host) and (host == active or host.endswith("." + active)) and not denied(host))


class Proxy(socketserver.StreamRequestHandler):
    def handle(self):
        first = self.rfile.readline(4097).decode("ascii", "replace").strip()
        match = re.fullmatch(r"CONNECT ([a-zA-Z0-9.-]+):443 HTTP/1\.[01]", first)
        try:
            active = ACTIVE.read_text().strip()
        except OSError:
            active = ""
        if not match or not permitted(match[1], active):
            self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        while True:
            line = self.rfile.readline(8193)
            if not line or line in (b"\r\n", b"\n"):
                break
            if len(line) > 8192:
                return
        try:
            upstream = socket.create_connection((match[1], 443), timeout=10)
        except OSError:
            self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            return
        with upstream:
            self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.wfile.flush()
            peers = (self.connection, upstream)
            while True:
                readable, _, _ = select.select(peers, [], [], 60)
                if not readable:
                    return
                for sender in readable:
                    try:
                        data = sender.recv(65536)
                        if not data:
                            return
                        (upstream if sender is self.connection else self.connection).sendall(data)
                    except OSError:
                        return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("127.0.0.1", 9223), Proxy) as server:
        server.serve_forever()
