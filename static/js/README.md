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
- `firebase-config.js` contains Firebase setup and App Check-related client logic.

## App Check status

Firebase App Check is intentionally disabled in the browser for this project. The related logic remains in `firebase-config.js`, but the active flag is set to `false` and the fetch injection is commented out.

This means the frontend sends normal requests without attaching `X-Firebase-AppCheck` tokens.

## Local development

When running locally, the frontend typically points to the local FastAPI API on port `8080` via the backend URL configuration.

Example:

```text
http://localhost:8080
```

## Deployment notes

The repo also includes Firebase hosting assets and deployment scripts. Those scripts are for deploying the frontend and backend in the project environment, but the current client-side App Check enforcement is disabled.
