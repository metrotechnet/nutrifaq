# Frontend JS overview

This folder contains the browser-side logic for the NutriFAQ interface.

## Main files

- `backend-url.js` sets the backend base URL used across the app.
- `config.js` handles app configuration and UI language state.
- `chat.js` manages message sending and streaming responses.
- `components.js` contains reusable UI widgets.
- `ui-utils.js` provides helper functions for layout and interaction behavior.
- `tts.js` handles browser text-to-speech playback.
- `voice-recognition.js` manages microphone and transcription flows.
- `agents.js` handles agent-specific actions and switching logic.
- `main.js` initializes the UI.

## Local development

When running locally, the frontend typically points to the local FastAPI API on port `8080` via the backend URL configuration.

Example:

```text
http://localhost:8080
```

## Deployment notes

The repo also includes Firebase hosting assets and deployment scripts.
