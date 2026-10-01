#!/usr/bin/env python3
"""Loopback-only static preview; never exposes .git or hidden files."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path("/home/hermes/vault/website")
PRIVATE = re.compile(r"(?i)^(secret|private)([._-]|$)|(?:\.env|auth\.json|\.pem|\.key)$")


class Handler(SimpleHTTPRequestHandler):
    def list_directory(self, path):
        self.send_error(403, "Directory listing is disabled")
        return None
    def translate_path(self, path):
        raw = unquote(urlsplit(path).path)
        pieces = Path(raw).parts
        if ".." in pieces or any(piece.startswith(".") or PRIVATE.search(piece) for piece in pieces if piece not in ("/", "")):
            return None
        candidate = ROOT / raw.lstrip("/")
        if ROOT.is_symlink() or any((ROOT.joinpath(*pieces[1:index + 1])).is_symlink() for index in range(1, len(pieces))):
            return None
        resolved = candidate.resolve()
        relative = resolved.relative_to(ROOT.resolve()) if resolved.is_relative_to(ROOT.resolve()) else None
        if relative is None or any(part.startswith(".") or PRIVATE.search(part) for part in relative.parts):
            return None
        return str(resolved)

    def send_head(self):
        if self.translate_path(self.path) is None:
            self.send_error(403, "Hidden and outside paths are forbidden")
            return None
        return super().send_head()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8899), Handler).serve_forever()
