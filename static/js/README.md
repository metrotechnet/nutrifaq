# Nutria Agent – Documentation
# JavaScript Modular Structure

This document describes the modular JavaScript frontend structure for the **Nutria Agent** project. It explains the purpose of each module and the rationale for the architecture.

## Overview
The frontend JavaScript code has been refactored from a single monolithic `script.js` file into a modular architecture with clear separation of concerns.

## Module Structure

### 0. **backend-url.js** - Backend URL Configuration
- **Purpose**: Sets `window.BACKEND_URL` for all other modules to use
- **Features**:
  - Auto-detects localhost:3000 → points to localhost:8080 for local dev
  - Auto-generated during Firebase deployment with production URL from `.env`
  - Must load first before any module that makes API calls
- **Exports**: `window.BACKEND_URL` (string)
- **Note**: This is a simple utility file, not a full module with exported functions

### 1. **config.js** - Configuration & Internationalization
- **Purpose**: Handles configuration loading and language management for single-agent setup
- **Key Functions**:
  - `loadConfig(agent)` - Load agent-specific configuration
  - `applyConfig(lang)` - Apply translations to DOM elements
  - `switchLanguage(lang)` - Change interface language
  - `populateSuggestionCards(lang)` - Populate suggestion cards
  - `t(key)` - Get translation for a key
- **Exports**: `window.ConfigModule`

### 2. **components.js** - Component Registry System
- **Purpose**: Manages reusable UI components
- **Components**:
  - `languageSelector` - Language pair selector for translation
  - `inputArea` - Input area configuration and visibility
- **Key Functions**:
  - `componentRegistry.languageSelector.render(config)` - Render language selector
  - `componentRegistry.inputArea.render(config)` - Render input area
- **Exports**: `window.ComponentsModule`

### 3. **ui-utils.js** - UI Utilities & Interactions
- **Purpose**: General UI helpers and interactions
- **Features**:
  - Mobile keyboard detection and handling
  - Scroll indicator management
  - Sidebar navigation
  - Cookie consent
  - Legal/privacy/about popups
- **Key Functions**:
  - `isMobileDevice()` - Detect mobile devices
  - `initKeyboardDetection()` - Initialize keyboard detection
  - `createScrollIndicator()` - Create scroll indicator
  - `initSidebar()` - Initialize sidebar
  - `showLegalNotice()`, `showPrivacyPolicy()`, `showAbout()` - Show popups
- **Exports**: `window.UIUtilsModule`

### 4. **chat.js** - Chat Messaging
- **Purpose**: Handles message sending, streaming, and UI
- **Key Functions**:
  - `sendMessage()` - Main message sending function
  - `createAssistantMessage()` - Create assistant message container
  - `setupMessageActions(messageDiv, contentDiv)` - Setup copy/share/like/TTS buttons
  - `handleStreamingResponse(question, contentDiv, actionsDiv)` - Handle SSE streaming
  - `scrollToMessageBottom()` - Scroll management
- **Exports**: `window.ChatModule`

### 5. **voice-recognition.js** - Voice Input
- **Purpose**: Voice recognition using Web Speech API and Whisper
- **Features**:
  - Web Speech API integration
  - Whisper transcription via backend
  - Auto-detection of source language for translation
- **Key Functions**:
  - `initSpeechRecognition()` - Initialize Web Speech API
  - `toggleRecording()` - Toggle voice recording
  - `initWhisperRecording()` - Start Whisper recording
  - `transcribeWithWhisper(audioBlob)` - Send audio to backend
- **Exports**: `window.VoiceRecognitionModule`

### 6. **tts.js** - Text-to-Speech
- **Purpose**: Read messages aloud using OpenAI TTS
- **Key Functions**:
  - `speakText(text, button)` - Speak text with TTS
  - `stopTTS()` - Stop current playback
  - `getActiveTtsButton()` - Get currently active TTS button
- **Exports**: `window.TTSModule`

### 7. **agents.js** - Agent Management
- **Purpose**: Handle agent switching and translation
- **Key Functions**:
  - `switchAgent(agent, userInitiated)` - Switch between agents
  - `sendTranslation()` - Handle translation requests
  - `renderAgentComponents(langData)` - Render agent-specific UI
  - `updateSourceLanguageDisplay()` - Update language display
- **Exports**: `window.AgentsModule`

### 8. **main.js** - Main Initialization
- **Purpose**: Initialize application and wire up all event handlers
- **Features**:
  - DOMContentLoaded initialization
  - Event handler setup for all buttons and inputs
  - Module initialization orchestration

## Load Order

The modules must be loaded in this specific order to resolve dependencies:

```html
<script src="/static/js/backend-url.js"></script>     <!-- Backend URL (sets window.BACKEND_URL) -->
<script src="/static/js/config.js"></script>          <!-- Config module (uses window.BACKEND_URL) -->
<script src="/static/js/components.js"></script>      <!-- Components need config -->
<script src="/static/js/ui-utils.js"></script>        <!-- UI utilities -->
<script src="/static/js/tts.js"></script>             <!-- TTS standalone -->
<script src="/static/js/chat.js"></script>            <!-- Chat needs config, ui-utils, tts -->
<script src="/static/js/voice-recognition.js"></script> <!-- Voice needs config, chat, agents -->
<script src="/static/js/agents.js"></script>          <!-- Agents need config, components, chat -->
<script src="/static/js/main.js"></script>            <!-- Main initializes everything last -->
```

## Module Communication

Modules communicate via the `window` object:
- Each module exports its public API to `window.[ModuleName]Module`
- Modules can access other modules' functions through these exports
- Example: `window.ConfigModule.getCurrentLanguage()`

## File Locations

### Development (Flask Backend)
- **Modules**: `/static/js/*.js`
- **HTML**: `/templates/index.html`
- **Script paths**: `/static/js/...`

### Production (Firebase Hosting)
- **Modules**: `/public/static/js/*.js`
- **HTML**: `/public/index.html`
- **Script paths**: `static/js/...` (no leading slash)

## Benefits of Modular Architecture

1. **Maintainability**: Each module has a single, clear responsibility
2. **Testability**: Modules can be tested independently
3. **Reusability**: Components can be reused across different agents
4. **Scalability**: Easy to add new modules or features
5. **Readability**: Smaller, focused files are easier to understand
6. **Debugging**: Errors are easier to locate and fix
7. **Collaboration**: Multiple developers can work on different modules

## Migration from script.js

The original `script.js` (~2500 lines) has been split into 9 focused modules:
- backend-url.js: ~10 lines (backend URL configuration)
- config.js: ~275 lines
- components.js: ~140 lines
- ui-utils.js: ~460 lines
- chat.js: ~455 lines
- voice-recognition.js: ~375 lines
- tts.js: ~130 lines
- agents.js: ~340 lines
- main.js: ~180 lines

**Total**: ~2365 lines (similar to original, but much better organized)

## Future Enhancements

Potential future modules:
- `analytics.js` - Usage analytics and tracking
- `notifications.js` - Toast/notification system
- `storage.js` - LocalStorage/SessionStorage management
- `api.js` - Centralized API call management
- `markdown.js` - Markdown rendering utilities
- `validation.js` - Input validation helpers

## Notes

- The original `script.js` files in `/static/` and `/public/static/` are kept for compatibility but should no longer be used
- Both HTML files (`templates/index.html` and `public/index.html`) have been updated to use the modular structure
- All modules are validated with no JavaScript errors
