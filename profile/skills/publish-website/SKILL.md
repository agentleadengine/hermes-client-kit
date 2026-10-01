---
name: publish-website
description: Build a client website, preview it privately, publish an approved version to the client's Netlify account, and undo it.
version: 1.0.0
license: MIT
---
# Publish a website

The client owns the Netlify account. Sam completes `kit-website setup-netlify SITE_ID` and adds `NETLIFY_AUTH_TOKEN` through `kit-set-key` during setup. Never ask for a token in chat, reveal it, or create another publishing route.

1. Work only in `/home/hermes/vault/website`. Keep the site static and include `index.html`. Do not include hidden files, credentials, private notes, or symlinks.
2. Call `starter_site_preview`. Give the client the private Tailscale preview address and describe the exact change. Sam runs `kit-tailscale preview` after joining the client's tailnet if the preview address is missing. Without a connected client tailnet, arrange a screen share before asking for approval.
3. Wait for the client's clear approval of that version by text. Call `starter_site_publish`. The tool's manual approval gate must pass. Report the returned Netlify URL and deployment ID only after Netlify confirms them.
4. If asked to undo, explain that the previous version will be redeployed and call `starter_site_undo` after fresh approval. Report the new deployment result.

Do not treat an earlier consent record as permission to publish a new version. Never use `git push` or a second deployment path for the Netlify site.
