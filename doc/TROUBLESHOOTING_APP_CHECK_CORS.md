# App Check CORS troubleshooting

This document is kept as historical reference. The current NutriFAQ project does not enforce Firebase App Check in the browser or backend, so the original CORS problem is not active in the current setup.

## Current behavior

Requests from the frontend are sent without App Check headers, which avoids the Firebase App Check CORS flow entirely.

## If you later re-enable App Check

Check the following:

1. Firebase project and App Check are configured correctly.
2. The web app is registered in Firebase.
3. reCAPTCHA keys match the Hosting domain.
4. The frontend and backend use the same project ID.
5. The browser does not block the App Check script due to a domain mismatch.

## Common causes when re-enabling

- domain not added to reCAPTCHA allowlist
- project ID mismatch between frontend and backend
- app not registered in Firebase on the correct project
- stale cached browser assets after config changes

## Suggested local fix

If you want to avoid App Check while debugging, keep the client flag disabled and do not register the middleware in `app.py`.

## Reference

- Firebase App Check docs: https://firebase.google.com/docs/app-check
- reCAPTCHA docs: https://developers.google.com/recaptcha/docs/v3
