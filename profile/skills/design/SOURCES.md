# Vendored design skills

These copies are vendored, never auto-updated. Review and commit any future update explicitly.

| Skill | Upstream repository | Commit SHA | License |
| --- | --- | --- | --- |
| frontend-design | https://github.com/anthropics/skills | `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4` | Apache-2.0 (`frontend-design/LICENSE.txt`) |
| webapp-testing | https://github.com/anthropics/skills | `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4` | Apache-2.0 (`webapp-testing/LICENSE.txt`) |
| ui-ux-pro-max | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | `09170eec67eefd46a7ae85de61b40c194020f997` | MIT (`ui-ux-pro-max/LICENSE`) |

`ui-ux-pro-max` search is local Python 3 standard-library code. The kit's optional starter step supplies system Chromium and a Python Playwright QA environment for Builder tests. The client agent itself keeps browser and terminal tools disabled.

Local adaptations replace Claude plugin paths with the installed Hermes profile path, use Python 3 and the kit QA environment in the webapp examples, and trim trailing whitespace in the vendored design-system script. The remaining upstream files stay in their named skill directories.

## 2026-10-01 client-kit additions

All copies below are vendored, never auto-updated. The source licenses are retained in each skill directory. The kit's consent, vault, and tool boundaries override upstream examples.

| Kit skill | Upstream repository | Exact commit | License | Local adaptation |
| --- | --- | --- | --- | --- |
| `office/docx` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`office/docx/LICENSE.upstream`) | Kit safety preface; local paths; no runtime install/download; office helpers use pinned venv |
| `office/xlsx` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`office/xlsx/LICENSE.upstream`) | Kit safety preface; local paths; no runtime install/download; office helpers use pinned venv |
| `office/pdf` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`office/pdf/LICENSE.upstream`) | Kit safety preface; local paths; no runtime install/download; office helpers use pinned venv |
| `office/powerpoint` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`office/powerpoint/LICENSE.upstream`) | Kit safety preface; local paths; no runtime install/download; office helpers use pinned venv |
| `business/weekly-review-planning` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`business/weekly-review-planning/LICENSE.upstream`) | Kit safety preface; external account/automation instructions removed or made consent-gated |
| `business/document-to-action-items` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`business/document-to-action-items/LICENSE.upstream`) | Kit safety preface; external account/automation instructions removed or made consent-gated |
| `business/meeting-action-items` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`business/meeting-action-items/LICENSE.upstream`) | Kit safety preface; external account/automation instructions removed or made consent-gated |
| `business/competitor-news-monitor` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`business/competitor-news-monitor/LICENSE.upstream`) | Kit safety preface; external account/automation instructions removed or made consent-gated |
| `business/grounded-citations` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`business/grounded-citations/LICENSE.upstream`) | Vault ledger path; removed optional installs and paid/API routes |
| `writing/humanizer` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`writing/humanizer/LICENSE.upstream`) | Kit safety preface; external account/automation instructions removed or made consent-gated |
| `design/popular-web-designs` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`design/popular-web-designs/LICENSE.upstream`) | Kit safety preface; external account/automation instructions removed or made consent-gated |
| `design/design-md` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`design/design-md/LICENSE.upstream`) | Removed Node CLI and npx workflow; kept offline spec guidance |
| `design/impeccable` | https://github.com/pbakaus/impeccable | `5a03dffc2708ece34c0c215e9449ca6cc3ec20ca` | Apache-2.0 (`design/impeccable/LICENSE`) | Kept SKILL.md and selected reference guidance only; removed launcher, detector, live-browser, download, hooks, npx, and script instructions; no scripts vendored. |
| `business/decision-questionnaire` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`business/decision-questionnaire/LICENSE.upstream`) | Optional upstream skill selected for local drafting; external actions and file paths constrained to the vault. |
| `business/one-three-one-rule` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`business/one-three-one-rule/LICENSE.upstream`) | Optional upstream skill selected for local drafting; external actions and file paths constrained to the vault. |
| `writing/social-media-content-calendar` | https://github.com/NousResearch/hermes-agent | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | MIT (`writing/social-media-content-calendar/LICENSE.upstream`) | Optional upstream skill selected for local drafting; external actions and file paths constrained to the vault. |

The added vendored guidance and helper source occupies about 1.6 MiB in this worktree. The pinned office environment is created at `/opt/hermes-kit/office-venv` during installation; budget roughly 100–180 MiB for its Python packages and venv. This runtime estimate has not been measured on a client droplet. It is separate from the optional Builder QA environment and Chromium.
