#!/usr/bin/env python3
"""Client-owned Lead and Deal Tracker, stdlib only."""
from __future__ import annotations
import csv
import hashlib
import hmac
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import parse_qs, urlparse
from access_jwt import verify

DATA = Path(os.environ.get("TOOL_DATA", "/data"))
DB = DATA / "tool.db"
ACCESS = Path(os.environ.get("TOOL_ACCESS_CONFIG", "/run/access.json"))
CERTS = Path(os.environ.get("TOOL_ACCESS_CERTS", "/run/access-certs.json"))
STAGES = ("New", "Contacted", "Qualified", "Proposal", "Won", "Lost")
DEAL_STAGES = ("Lead", "Qualified", "Under contract", "Closing", "Closed")


def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def csrf_token():
    key = DATA / "csrf.key"
    if not key.exists():
        key.write_bytes(secrets.token_bytes(32))
        key.chmod(0o600)
    return hmac.new(key.read_bytes(), b"lead-tracker-form", hashlib.sha256).hexdigest()


def esc(value):
    return html.escape(str(value), quote=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, code, body, content_type="text/html; charset=utf-8", headers=None):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        try:
            cfg = json.loads(ACCESS.read_text())
            if cfg.get("mode") == "tailscale":
                login = self.headers.get("Tailscale-User-Login", "")
                return bool(login and len(login) <= 320 and "\n" not in login and "\r" not in login)
            certs = json.loads(CERTS.read_text())
            age = __import__("time").time() - certs["fetched_at"]
            if not 0 <= age <= 86400:
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
        return verify(self.headers.get("Cf-Access-Jwt-Assertion", ""), cfg, fetch=lambda _: json.dumps(certs).encode())

    def page(self, title, body):
        return f'<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>{esc(title)}</title><style>body{{font:16px system-ui;max-width:65rem;margin:2rem auto;padding:0 1rem}}nav a{{margin-right:1rem}}table{{border-collapse:collapse;width:100%}}td,th{{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}}input,select,textarea{{font:inherit;padding:.4rem;max-width:100%}}button{{padding:.5rem 1rem}}</style></head><body><nav><a href="/">Follow-ups</a><a href="/contacts">Contacts</a><a href="/pipeline">Pipeline</a><a href="/closings">Closings</a><a href="/export.csv">Export CSV</a></nav><h1>{esc(title)}</h1>{body}</body></html>'

    def do_GET(self):
        if not self.authorized():
            self.respond(403, "Access token required", "text/plain")
            return
        if (DATA / "maintenance").exists():
            self.respond(503, "Maintenance in progress", "text/plain")
            return
        path = urlparse(self.path).path
        with connect() as db:
            if path == "/health":
                db.execute("SELECT 1 FROM contacts LIMIT 1").fetchall()
                self.respond(200, '{"ok":true}', "application/json")
            elif path == "/export.csv":
                out = io.StringIO()
                writer = csv.writer(out)
                writer.writerow(["name", "email", "phone", "kind", "source", "stage", "next_follow_up", "notes"])
                writer.writerows(db.execute("SELECT name,email,phone,kind,source,stage,next_follow_up,notes FROM contacts ORDER BY id"))
                self.respond(200, out.getvalue(), "text/csv; charset=utf-8", {"Content-Disposition": "attachment; filename=contacts.csv"})
            elif path in ("/", "/contacts"):
                today = __import__("datetime").date.today().isoformat()
                rows = db.execute("SELECT * FROM contacts WHERE (? = '/contacts' OR next_follow_up <= ? AND next_follow_up != '') ORDER BY next_follow_up,id LIMIT 500", (path, today))
                table = "<table><tr><th>Name</th><th>Kind</th><th>Stage</th><th>Follow up</th><th>Notes</th></tr>" + "".join(f"<tr><td>{esc(r['name'])}</td><td>{esc(r['kind'])}</td><td>{esc(r['stage'])}</td><td>{esc(r['next_follow_up'])}</td><td>{esc(r['notes'])}</td></tr>" for r in rows) + "</table>"
                form = f'<h2>Add contact</h2><form method="post" action="/contacts"><input type="hidden" name="csrf" value="{csrf_token()}"><label>Name <input name="name" required maxlength="120"></label><label>Email <input name="email" maxlength="200"></label><label>Phone <input name="phone" maxlength="40"></label><label>Kind <select name="kind"><option>lead</option><option>buyer</option><option>seller</option></select></label><label>Source <input name="source" maxlength="120"></label><label>Stage <select name="stage">' + "".join(f"<option>{s}</option>" for s in STAGES) + '</select></label><label>Follow up <input name="next_follow_up" type="date"></label><label>Notes <textarea name="notes" maxlength="2000"></textarea></label><button>Add</button></form>'
                self.respond(200, self.page("Contacts" if path == "/contacts" else "Today's follow-ups", table + form))
            elif path in ("/pipeline", "/closings"):
                if path == "/pipeline":
                    rows = db.execute("SELECT deals.title,deals.stage,deals.closing_date,contacts.name FROM deals JOIN contacts ON contacts.id=deals.contact_id ORDER BY deals.stage,deals.id")
                else:
                    month = __import__("datetime").date.today().isoformat()[:7]
                    rows = db.execute("SELECT deals.title,deals.stage,deals.closing_date,contacts.name FROM deals JOIN contacts ON contacts.id=deals.contact_id WHERE closing_date LIKE ? ORDER BY closing_date", (month + "%",))
                table = "<table><tr><th>Deal</th><th>Contact</th><th>Stage</th><th>Close</th></tr>" + "".join(f"<tr><td>{esc(r['title'])}</td><td>{esc(r['name'])}</td><td>{esc(r['stage'])}</td><td>{esc(r['closing_date'])}</td></tr>" for r in rows) + "</table>"
                self.respond(200, self.page("Pipeline" if path == "/pipeline" else "This month's closings", table))
            else:
                self.respond(404, "Not found", "text/plain")

    def do_POST(self):
        if not self.authorized():
            self.respond(403, "Access token required", "text/plain")
            return
        if (DATA / "maintenance").exists():
            self.respond(503, "Maintenance in progress", "text/plain")
            return
        if urlparse(self.path).path != "/contacts" or int(self.headers.get("Content-Length", "0")) > 8192:
            self.respond(400, "Invalid request", "text/plain")
            return
        fields = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode(), keep_blank_values=True)
        get = lambda key: fields.get(key, [""])[0].strip()
        if not hmac.compare_digest(get("csrf"), csrf_token()) or not 1 <= len(get("name")) <= 120 or get("kind") not in {"lead", "buyer", "seller"} or get("stage") not in STAGES:
            self.respond(400, "Invalid contact", "text/plain")
            return
        if any(len(get(k)) > limit for k, limit in (("email", 200), ("phone", 40), ("source", 120), ("notes", 2000))):
            self.respond(400, "Field too long", "text/plain")
            return
        with connect() as db:
            cursor = db.execute("INSERT INTO contacts(name,email,phone,kind,source,stage,next_follow_up,notes) VALUES (?,?,?,?,?,?,?,?)", tuple(get(k) for k in ("name", "email", "phone", "kind", "source", "stage", "next_follow_up", "notes")))
            db.execute("INSERT INTO audit(actor,action,entity,entity_id) VALUES (?,?,?,?)", ("client", "create", "contact", cursor.lastrowid))
        self.send_response(303)
        self.send_header("Location", "/contacts")
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
