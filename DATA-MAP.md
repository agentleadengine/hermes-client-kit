# Data map

This map is completed with the client during onboarding. It is deliberately specific about where data goes.

| Service | Data it may receive | Purpose | Client decision | Disconnect path |
| --- | --- | --- | --- | --- |
| Model provider | TODO: prompts and approved tool results | Generate responses | TODO | Remove provider key with `kit-set-key` replacement and revoke at provider |
| AgentMail | TODO: only messages the client forwards to the agent inbox | Draft and summarize email | Optional | Revoke the inbox-scoped key and delete the inbox |
| SearXNG | Search queries | Private web research | Optional | Stop `searxng.service` |
| Syncthing | Vault files selected by the client | Client device sync | Optional | Remove pairing in its loopback UI |
| Netlify | Approved public website files, site ID, deployment metadata, and the client-owned deploy token | Publish the client's website | Starter consent plus approval for each publish | `kit-powerup off netlify`, then revoke the token in Netlify |
| Tailscale | Server and permitted device identities, private tool traffic, and connection metadata | Let the client's devices reach tools privately | Starter consent and a client one-use join key during setup | `kit-tailscale down`, then remove the device in the client's Tailscale account |
| Local video renderer | Script text and screenshots stay on the server | Create captioned MP4 files | Starter media consent | `kit-powerup off media` |
| Speech API, only if enabled | Text of a video script and the client-owned TTS key | Optional spoken narration | Separate key consent and approval for each paid video | `kit-powerup off media`, then revoke the key with the provider |
| Approved integration | TODO: exact scopes and data types | Client-selected task | Optional | Use the provider disconnect flow, remove the credential, and run `kit-consent remove` |

The agent must refuse to store patient records, legal case files, Social Security numbers, payment card numbers, bank logins, passwords, or recovery codes.
