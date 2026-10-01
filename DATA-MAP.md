# Data map

This map is completed with the client during onboarding. It is deliberately specific about where data goes.

| Service | Data it may receive | Purpose | Client decision | Disconnect path |
| --- | --- | --- | --- | --- |
| Model provider | TODO: prompts and approved tool results | Generate responses | TODO | Remove provider key with `kit-set-key` replacement and revoke at provider |
| AgentMail | TODO: only messages the client forwards to the agent inbox | Draft and summarize email | Optional | Revoke the inbox-scoped key and delete the inbox |
| SearXNG | Search queries | Private web research | Optional | Stop `searxng.service` |
| Syncthing | Vault files selected by the client | Client device sync | Optional | Remove pairing in its loopback UI |
| Approved integration | TODO: exact scopes and data types | Client-selected task | Optional | Use the provider disconnect flow, remove the credential, and run `kit-consent remove` |

The agent must refuse to store patient records, legal case files, Social Security numbers, payment card numbers, bank logins, passwords, or recovery codes.
