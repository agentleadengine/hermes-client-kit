# Your assistant

You can text your assistant in the messaging app Sam set up for you. Only your approved account can reach it. Your assistant keeps drafts and files on your server. You own the accounts used to publish a website or connect your devices.

For iMessage, enter your phone number on the activation page, open the Photon approval link on your phone, and tap Approve. The manual project ID and secret path is available only if device login cannot be used. For ChatGPT sign-in, first turn on **Settings > Security and login > Enable device code sign-in for Codex, Excel, PowerPoint, and Word**; then use the activation page's sign-in code.

After chat setup, tap the prefilled **Hi** link and send it from your approved phone. Photon and Telegram cannot start a conversation with a number that has not messaged first. Your first reply includes your name and three sample texts chosen from your business packs.

Sam fills in your Business Brief during setup so your assistant knows your business, prices, usual answers, and writing style. It saves a short memory summary only with your recorded consent. You can ask to review or update the brief any time.

## What you can text your assistant

- “Research this question and show me the sources.” Ask for a short answer, a draft, or notes saved for later.
- “Make a page for my business.” Your assistant can build or change files for your website, then show you a private preview. Text your approval for that exact version before it publishes to your Netlify account. If the result is wrong, ask it to restore the previous version.
- “Make a small tool to track this.” Your assistant can draft and test a tool in a separate work area. It asks before publishing or rolling back a version. Your tools can be reached from your own devices after Sam connects the server to your Tailscale network.
- “Make me a dashboard for my jobs.” Your assistant asks six short questions, shows a simple plan, then builds a phone-friendly draft after you say yes. It sends a screenshot for review and asks again before putting the tool live.
- “Turn this script into a tutorial video.” Send a short script and, if useful, screenshots. Your assistant saves an MP4 in your server's files. Voice is off unless you add your own speech key and approve that video's paid voice request.
- “Save these notes and organize them.” Memory changes still need your approval.
- “Remind me Friday at 9 to call Dana.” With Schedules on, your assistant can create, list, pause, and cancel reminders sent only to your approved chat. Ask it to turn on the paused Monday plan or Friday wrap if you want them.

Publishing, changing a live tool, and paid voice generation require a fresh approval for each action. A request to research a topic is never approval to publish it. Your assistant cannot read your mailbox, move money, open banking or payroll sites, or ask you to send passwords or codes by text.

## Advanced: your server

Sam sets up the server with you. During setup, you choose which capabilities to enable. The server records each choice. Sam adds your Netlify token through a hidden local prompt and joins your Tailscale network with a one-use key. The server does not join any network just because the software is installed.

Your website files live in `/home/hermes/vault/website`. Video files live in `/home/hermes/vault/media`. Tool drafts live in `/home/hermes/vault/tools`. The website preview gets a private address on your Tailscale network, so you can review it from one of your devices before approval. Tailscale makes selected tools available only to devices allowed by your own network settings. Sam can show you how to add or remove devices in your Tailscale account.

On the server, `kit-verify` checks the safety settings and installed capabilities. `kit-health --explain` shows a status report without your messages or files. `kit-powerup off netlify`, `kit-powerup off media`, or `kit-powerup off tailscale` stops the corresponding capability. To remove the server from your network, use `kit-tailscale down` as well. Ask Sam to walk through these commands on a screen share if you prefer.

The starter profile includes `build-dashboard`, reviewed office, business, writing, and design guidance, and private design testing through `webapp-testing`. The last skill runs in the isolated Builder test lane when Builder or Website is enabled; it does not give the assistant general browser access. The kit reuses its installed Chromium and adds a Python Playwright environment only for those optional capabilities. Budget roughly 50–100 MB for the Python environment plus several hundred MB for Chromium on a fresh server; actual installed size depends on package versions and must be measured on the server.
