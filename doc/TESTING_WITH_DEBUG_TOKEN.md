# Debug token notes

This file documents the older Firebase App Check debug-token approach. The current project no longer uses App Check, so this workflow is not active by default.

## Current project state

- Frontend App Check is disabled in `static/js/firebase-config.js`
- Backend App Check middleware is not enabled in `app.py`
- No App Check token is required for local API requests

## If you re-enable App Check later

You would normally:

1. Configure Firebase App Check in the Firebase Console
2. Add a valid debug token for local testing
3. Set `APP_CHECK_ENABLED=true` in the environment
4. Ensure your web app is correctly registered for reCAPTCHA or debug tokens

## Example environment values

```bash
APP_CHECK_ENABLED=true
FIREBASE_PROJECT_ID=your-project-id
APP_CHECK_DEBUG=true
```

## Important

Do not rely on debug tokens for production usage. They are only for local troubleshooting and development testing.

## Reference

- Firebase App Check docs: https://firebase.google.com/docs/app-check
- Firebase debug provider docs: https://firebase.google.com/docs/app-check/web/debug-provider
