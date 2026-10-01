#!/usr/bin/env python3
"""Loopback-only static preview; never exposes .git or hidden files."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path("/home/hermes/vault/website")


class Handler(SimpleHTTPRequestHandler):
    def list_directory(self, path):
        self.send_error(403, "Directory listing is disabled")
        return None
    def translate_path(self, path):
        raw = unquote(urlsplit(path).path)
        pieces = Path(raw).parts
        if ".." in pieces or any(piece.startswith(".") for piece in pieces if piece not in ("/", "")):
            return "/dev/null"
        candidate = (ROOT / raw.lstrip("/")).resolve()
        return str(candidate) if candidate.is_relative_to(ROOT.resolve()) else "/dev/null"


ThreadingHTTPServer(("127.0.0.1", 8899), Handler).serve_forever()
