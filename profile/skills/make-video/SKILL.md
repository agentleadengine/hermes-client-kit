---
name: make-video
description: Turn a short text script and optional vault screenshots into a captioned MP4.
version: 1.0.0
license: MIT
---
# Make a video

Create a short `.txt` or `.md` script in `/home/hermes/vault`. Separate title cards and steps with blank lines. Keep each card under 260 characters. To show a screenshot, put `[[image:path/to/screenshot.png]]` on the first line of that card, with the path relative to the vault.

Call `starter_make_video` with the script path and a simple `.mp4` output name. The result is saved under `/home/hermes/vault/media`. The normal path uses local ffmpeg and no paid API. To add voice, the client must first add their own `TTS_API_KEY` through `kit-set-key`; ask for explicit approval for this video because the speech API costs money and receives the script text. The tool enforces that approval. Tell the client when a voice is AI generated.

To share the MP4 publicly, call `starter_video_share` with the output filename. This only adds it to the website draft. Then use the `publish-website` preview and approval flow. Do not upload a video by another route.
