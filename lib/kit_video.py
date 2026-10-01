"""Render short captioned tutorial cards with ffmpeg, entirely in the vault."""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

VAULT = Path(os.environ.get("KIT_VIDEO_VAULT", "/home/hermes/vault"))
LEDGER = Path(os.environ.get("KIT_VIDEO_LEDGER", "/etc/hermes-kit/consents.json"))
ENV = Path(os.environ.get("KIT_VIDEO_ENV", "/home/hermes/.hermes/profiles/client/.env"))
TEST = os.environ.get("KIT_VIDEO_TEST_MODE") == "1"


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def consent(name):
    return LEDGER.exists() and any(x.get("integration") == name for x in json.loads(LEDGER.read_text()).get("consents", []))


def under_vault(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(VAULT.resolve()) or path.is_symlink():
        raise ValueError("Video inputs and outputs must be regular files inside the vault")
    return resolved


def cards(script: str):
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", script) if block.strip()]
    if not paragraphs or len(paragraphs) > 30:
        raise ValueError("A video needs 1-30 short cards")
    result = []
    for block in paragraphs:
        image = None
        lines = block.splitlines()
        if lines[0].startswith("[[image:") and lines[0].endswith("]]"):
            image = under_vault(VAULT / lines.pop(0)[8:-2])
            if image.suffix.lower() not in {".png", ".jpg", ".jpeg"} or not image.is_file():
                raise ValueError("Screenshot must be a PNG or JPEG in the vault")
            if image.stat().st_size > 8_000_000:
                raise ValueError("Screenshot exceeds the 8 MB video limit")
        text = " ".join(line.strip() for line in lines).strip()
        if not text or len(text) > 260:
            raise ValueError("Each card needs 1-260 characters of caption text")
        result.append((text, image))
    return result


def speech(text: str, destination: Path):
    match = re.search(r'^TTS_API_KEY="([A-Za-z0-9_-]+)"$', ENV.read_text(), re.MULTILINE)
    key = match.group(1) if match else None
    if not key:
        raise ValueError("Add your own TTS_API_KEY before requesting voice")
    request = Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps({"model": "gpt-4o-mini-tts-2025-12-15", "voice": "alloy", "input": text, "response_format": "mp3"}).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        audio = response.read(10_000_001)
        if len(audio) > 10_000_000:
            raise ValueError("Speech response exceeds the 10 MB video limit")
        destination.write_bytes(audio)


def render_card(caption: str, screenshot: Path | None, html_file: Path, image_file: Path):
    browser = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser:
        raise ValueError("Chromium is required for the HTML video renderer")
    image_markup = ""
    if screenshot:
        kind = "image/png" if screenshot.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(screenshot.read_bytes()).decode()
        image_markup = f'<img alt="Tutorial screenshot" src="data:{kind};base64,{encoded}">'
    html_file.write_text(
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        'html,body{margin:0;width:1280px;height:720px;background:#182333;color:white;font:44px system-ui;overflow:hidden}'
        'main{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:30px}'
        'img{max-width:1120px;max-height:480px;object-fit:contain;border:3px solid #8aa1bd}'
        'p{max-width:1120px;margin:0;padding:18px 28px;text-align:center;background:#101722;line-height:1.2}'
        '</style></head><body><main>' + image_markup + '<p>' + html.escape(caption) + '</p></main></body></html>'
    )
    run([browser, "--headless", "--disable-gpu", "--disable-javascript", "--disable-extensions", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--window-size=1280,720", "--force-device-scale-factor=1", f"--screenshot={image_file}", html_file.as_uri()], capture_output=True)
    if not image_file.is_file():
        raise ValueError("Chromium did not render the video card")


def render(script_path: Path, output_name: str, voice: bool = False, approve_paid: bool = False):
    if not TEST and not consent("media"):
        raise ValueError("Media consent is missing")
    if voice and (not approve_paid or not consent("env:TTS_API_KEY")):
        raise ValueError("Voice needs the client's TTS key consent and per-video paid-action approval")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.mp4", output_name):
        raise ValueError("Output must be a simple .mp4 filename")
    script_path = under_vault(script_path)
    if not script_path.is_file() or script_path.suffix.lower() not in {".txt", ".md"}:
        raise ValueError("Script must be a text file in the vault")
    if script_path.stat().st_size > 64_000:
        raise ValueError("Script exceeds the 64 KB video limit")
    sequence = cards(script_path.read_text())
    output = VAULT / "media" / output_name
    output.parent.mkdir(parents=True, exist_ok=True)
    under_vault(output.parent)
    with tempfile.TemporaryDirectory(prefix="work-", dir=output.parent) as directory:
        temp = Path(directory)
        clips = []
        for index, (caption, image) in enumerate(sequence):
            html_file = temp / f"card-{index}.html"
            image_file = temp / f"card-{index}.png"
            render_card(caption, image, html_file, image_file)
            audio = temp / f"voice-{index}.mp3"
            duration = 4.0
            if voice:
                speech(caption, audio)
                probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio)], capture_output=True, text=True)
                duration = max(4.0, float(probe.stdout.strip()) + 0.4)
            source = ["-loop", "1", "-i", str(image_file)]
            fade_out = max(0.0, duration - 0.4)
            filter_text = f"fade=t=in:st=0:d=0.4,fade=t=out:st={fade_out:.2f}:d=0.4"
            clip = temp / f"card-{index:02}.mp4"
            args = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *source]
            if voice:
                args += ["-i", str(audio)]
            args += ["-t", f"{duration:.2f}", "-vf", filter_text, "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
            if voice:
                args += ["-c:a", "aac", "-shortest"]
            args.append(str(clip))
            run(args)
            clips.append(clip)
        listing = temp / "clips.txt"
        listing.write_text("".join(f"file '{clip}'\n" for clip in clips))
        run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(output)])
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument("output")
    parser.add_argument("--voice", action="store_true")
    parser.add_argument("--approve-paid", action="store_true")
    args = parser.parse_args()
    print(render(args.script, args.output, args.voice, args.approve_paid))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
