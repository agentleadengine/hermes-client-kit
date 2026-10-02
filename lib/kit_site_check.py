#!/usr/bin/env python3
"""Narrow local-browser check for an already staged website preview."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8899/"


def allowed(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == 8899
    except ValueError:
        return False


def check(output: Path) -> dict:
    browser_path = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser_path:
        raise ValueError("Kit Chromium is missing")
    output.mkdir(parents=True, exist_ok=True)
    issues = []
    previews = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=browser_path, args=["--disable-background-networking"])
        try:
            for label, width, height in (("phone", 390, 844), ("desktop", 1440, 900)):
                context = browser.new_context(viewport={"width": width, "height": height}, service_workers="block")
                context.route("**/*", lambda route: route.continue_() if allowed(route.request.url) else route.abort())
                context.route_web_socket("**/*", lambda socket: socket.close())
                page = context.new_page()
                page.on("console", lambda message: issues.append(f"{label}: console {message.text[:160]}") if message.type == "error" else None)
                page.on("pageerror", lambda error: issues.append(f"{label}: script {str(error)[:160]}"))
                response = page.goto(URL, wait_until="networkidle", timeout=15000)
                if not response or response.status != 200:
                    issues.append(f"{label}: preview did not load successfully")
                if page.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
                    issues.append(f"{label}: page overflows sideways")
                image = output / f"{label}.png"
                page.screenshot(path=str(image), full_page=True)
                previews[label] = str(image)
                for index in range(page.get_by_role("button").count()):
                    button = page.get_by_role("button").nth(index)
                    if not button.is_visible() or not button.is_enabled():
                        continue
                    name = button.inner_text()[:80] or f"button {index + 1}"
                    try:
                        button.click(timeout=2000)
                    except Exception as error:
                        issues.append(f"{label}: {name} could not be clicked ({str(error)[:100]})")
                context.close()
        finally:
            browser.close()
    return {"previews": previews, "issues": issues}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: kit_site_check.py OUTPUT_DIR")
    print(json.dumps(check(Path(sys.argv[1]))))
