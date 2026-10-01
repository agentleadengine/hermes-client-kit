# Agent Care wire contract v1 (client server <-> HQ)

Single source of truth shared by ~/hermes-client-kit (the box) and ~/agent-care-hq (HQ). Both repos keep a byte-identical copy
of this folder (kit: `contract/`). Changing it = bump the version, update both sides, update fixtures in both test suites.

## 1. Identities
- `agent_id`: `A` + 2-4 digits, e.g. `A07`. Pseudonym only; never a business name. Regex `^A[0-9]{2,4}$`.
- Box key: ed25519, generated on the box by `kit-enroll`, private key `/etc/hermes-kit/report/box_ed25519.pem` root 0600.
  Public key sent as base64 of the 32-byte raw key (`pub_b64`).
- Fingerprint words: `sha256(raw 32-byte public key)`; take bytes 0..3; each byte indexes `fingerprint-words.txt`
  (256 lines, 0-based). Shown as 4 words joined by spaces. Both sides must compute the same 4 words (fixture in §7).

## 2. Provisioning registers the agent (server to server)
`POST /api/agents` on HQ. Auth: header `Authorization: Bearer <HQ_PROVISION_TOKEN>` (env on both Netlify sites).
Body: `{"agent_id":"A07","client_ref":"<intake job id>","droplet_ip":"203.0.113.9","code_sha256":"<hex>","expires_at":"<ISO8601 UTC>","tier":"care|managed|full"}`
HQ stores agent `state=REGISTERED`. The raw enrollment code (32 random bytes, base64url) goes only into the box's kit.conf
as `KIT_ENROLL_CODE`, next to `KIT_AGENT_ID` and `KIT_HQ_URL`. Code lifetime 48 h, single use.

## 3. Enrollment (box -> HQ, first boot)
`POST /api/enroll`. Body:
`{"v":1,"agent_id":"A07","pub_b64":"...","ts":"<ISO8601 UTC>","code":"<raw code>","sig_b64":"<ed25519 sig over UTF-8 of: 'enroll|'+agent_id+'|'+pub_b64+'|'+ts+'|'+code>"}`
HQ accepts only if ALL hold: agent REGISTERED and not expired; `sha256(code)==code_sha256`; source IP (Netlify `x-nf-client-connection-ip`)
== `droplet_ip`; `ts` within ±10 min; signature valid for `pub_b64`; fewer than 5 attempts. Then: store pub key, `state=PENDING`,
burn code, audit event. Any later enroll for the same agent: 409, audit + alert `ENROLL_CONFLICT` (P0). Response `{"ok":true,"words":"w1 w2 w3 w4"}`.
Activation: Sam runs `care enroll confirm A07`; HQ shows the words; on confirm `state=ACTIVE`. `care enroll remint A07`
(allowed only before handover) issues a new code hash for a fresh `kit-enroll --reset`.

## 4. Health push (box -> HQ, every 5 minutes)
`POST /api/ingest`. Headers: `Content-Type: application/json`, `X-AC-Agent: A07`, `X-AC-Signature: <base64 ed25519 sig over the exact raw body bytes>`.
Body envelope: `{"v":1,"agent_id":"A07","sent_at":"<ISO8601 UTC>","nonce":"<32 hex>","payload":{...health schema 3...}}`
HQ accepts only if: agent ACTIVE; signature valid over raw bytes; `sent_at` within ±10 min; nonce unseen for this agent in 24 h;
payload validates against `health-schema-v3.json` with **no additional properties anywhere**. Rejections: 401 bad sig/unknown
agent, 409 replay, 422 schema. A 422 raises alert `LEAK_GUARD` (P0) because an unknown field may be leaking content.
Box behavior: 10 s timeout, jittered retry, never blocks the agent, records `push.failures_since_last_ok` in the next payload.
On clean shutdown the box sends one final push with `going_down:true`.

## 5. Health schema 3
Schema 3 = the current kit-health schema 2 (bin/kit-health) plus the fields below. Full JSON Schema: `health-schema-v3.json`.
Added: `agent_id`, `tier` (`care|managed|full`), `handover_done` (bool), `going_down` (bool),
`planned_downtime_until` (ISO8601 or `"none"`), `power_ups` (array, closed set `base|builder|website|logins|schedules`),
`tools` (array of `{name:^[a-z][a-z0-9-]{1,31}$, up:bool, version:^[0-9A-Za-z._-]{1,40}$, last_backup_ok_hours:number>=0, tests_ok:bool}`, max 20),
`access` (`{manager_key_present:bool, full_access_active:bool, grants_active:int>=0, grant_expires_at:ISO8601|"none", team_key_fingerprints?:string[]}`). The optional `team_key_fingerprints` contains SSH public key fingerprints in `SHA256:<base64>` form so HQ can confirm a team key was revoked. Older boxes may omit it; revocations remain pending until a box reports it.
`push` (`{failures_since_last_ok:int>=0}`). `schema` becomes 3. Never: messages, prompts, file/vault names, memory text,
contact names, hostnames, IPs, URLs, secrets, raw logs, tool data.

## 6. Release channel (box pulls from GitHub)
Existing: signed tags + signed manifest per tag (bin/kit-autoupdate). New: signed stable pointer replaces the static
`KIT_CANARY_PROMOTED_SEQUENCE`. File `releases/stable.json` = `{"v":1,"sequence":N,"tag":"vX.Y.Z","signed_at":"...","expires_at":"..."}`
with `releases/stable.json.sig` = `ssh-keygen -Y sign -n hermes-kit-pointer` by an allowed signer (same allowed_signers file,
namespace `hermes-kit-pointer`). Hosted on the kit repo's `releases` branch, fetched from `${KIT_RELEASE_MANIFEST_URL%/}/stable.json`.
Box rules: verify signature + unexpired; apply a release only if `manifest.sequence <= pointer.sequence` and the manifest's 72 h
age rule holds; pointer sequence must never go backwards (persisted). `KIT_CHANNEL=canary` boxes ignore the pointer (still
require signatures). `care release promote vX.Y.Z` writes, signs and pushes the pointer.

## 7. Fixtures (both test suites use these)
`fixtures/` holds: a test ed25519 key pair (test only, never deployed), a valid schema-3 payload, a payload with one unknown
field, a signed ingest body + signature, an enroll body + signature, and `expected-words.txt` for the test public key.
Generate fixtures once with `fixtures/make-fixtures.mjs` (Node crypto) and commit the outputs.
