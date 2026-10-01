# Your assistant

You can text your assistant in the messaging app Sam set up for you. Only your approved account can reach it. Your assistant keeps drafts and files on your server. You own the accounts used to publish a website or connect your devices.

## What you can text your assistant

- “Research this question and show me the sources.” Ask for a short answer, a draft, or notes saved for later.
- “Make a page for my business.” Your assistant can build or change files for your website, then show you a private preview. Text your approval for that exact version before it publishes to your Netlify account. If the result is wrong, ask it to restore the previous version.
- “Make a small tool to track this.” Your assistant can draft and test a tool in a separate work area. It asks before publishing or rolling back a version. Your tools can be reached from your own devices after Sam connects the server to your Tailscale network.
- “Turn this script into a tutorial video.” Send a short script and, if useful, screenshots. Your assistant saves an MP4 in your server's files. Voice is off unless you add your own speech key and approve that video's paid voice request.
- “Save these notes and organize them.” Memory changes still need your approval.

Publishing, changing a live tool, and paid voice generation require a fresh approval for each action. A request to research a topic is never approval to publish it. Your assistant cannot read your mailbox, move money, open banking or payroll sites, or ask you to send passwords or codes by text.

## Advanced: your server

Sam sets up the server with you. During setup, you choose which capabilities to enable. The server records each choice. Sam adds your Netlify token through a hidden local prompt and joins your Tailscale network with a one-use key. The server does not join any network just because the software is installed.

Your website files live in `/home/hermes/vault/website`. Video files live in `/home/hermes/vault/media`. Tool drafts live in `/home/hermes/vault/tools`. The website preview gets a private address on your Tailscale network, so you can review it from one of your devices before approval. Tailscale makes selected tools available only to devices allowed by your own network settings. Sam can show you how to add or remove devices in your Tailscale account.

On the server, `kit-verify` checks the safety settings and installed capabilities. `kit-health --explain` shows a status report without your messages or files. `kit-powerup off netlify`, `kit-powerup off media`, or `kit-powerup off tailscale` stops the corresponding capability. To remove the server from your network, use `kit-tailscale down` as well. Ask Sam to walk through these commands on a screen share if you prefer.
