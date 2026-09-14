# Firebase App Check setup notes

This document is kept for reference, but the current NutriFAQ implementation does not enforce Firebase App Check in the browser or backend.

## Current status

- Frontend App Check is disabled in `static/js/firebase-config.js`
- Backend App Check middleware is not registered in `app.py`
- Requests do not require an `X-Firebase-AppCheck` header

## Why this project is configured this way

The project is currently being used in a local/development-friendly configuration where App Check is intentionally off to avoid blocking requests during testing and iteration.

## If you want to re-enable it later

1. Set `APP_CHECK_ENABLED=true` in the backend environment if needed.
2. Re-enable the App Check middleware in `app.py`.
3. Restore the frontend config in `static/js/firebase-config.js`.
4. Configure Firebase App Check and reCAPTCHA keys in the Firebase Console.

## Typical configuration to re-enable

```bash
APP_CHECK_ENABLED=true
FIREBASE_PROJECT_ID=your-project-id
RECAPTCHA_SITE_KEY=your-site-key
```

## References

- Firebase App Check docs: https://firebase.google.com/docs/app-check
- reCAPTCHA v3 docs: https://developers.google.com/recaptcha/docs/v3
