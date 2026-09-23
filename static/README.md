# Static frontend overview

This folder contains the web frontend assets used by the NutriFAQ UI.

## Folder structure

```text
static/
├── css/              # split stylesheets (layout, chat, publish, mobile, etc.)
├── js/               # browser logic (chat, config, download-manager, auth, etc.)
├── locales/          # i18n dictionaries (fr.json, en.json)
├── config/           # runtime frontend config files
├── logos/            # branding assets
└── README.md
```

## Key frontend modules

- `js/chat.js`: chat flow, streaming response rendering, and message lifecycle.
- `js/ui-utils.js`: shared UI helpers, including scroll indicator logic.
- `js/download-manager.js`: download/index/publish panel behavior, logs tabs, reset, and PDF export.
- `js/config.js`: language and runtime config plumbing.
- `js/auth.js`: auth-related UI wiring and token handling.

## Publish logs UX (recent behavior)

- The logs panel has two tabs:
  - `Conversations` (question logs)
  - `Publications` (publish operation logs)
- Default tab is `Conversations`.
- `Reset` action is enabled for question logs and shows a confirmation popup.
- `Export` generates a PDF with a tab-specific title:
  - Questions: `Rapport d'activite : Discussions`
  - Publish: `Rapport d'activite : Publications`

## Styling notes

- Text contrast was adjusted to improve readability in shell/chat/publish/cookie areas.
- Do frontend edits in `static/` (not in `public/`), then validate rendered pages.

## Locales

- Strings are loaded through translation keys in `locales/fr.json` and `locales/en.json`.
- Prefer adding/updating i18n keys instead of hardcoding user-facing text in JS.
