# Firebase App Check Setup Guide

## Overview
Firebase App Check protects your API endpoints from unauthorized access by verifying that requests come from legitimate app instances.

## Setup Steps

### 1. Firebase Console Configuration

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project: `${FIREBASE_PROJECT_ID}`
3. Navigate to **Project Settings** > **App Check**
4. Click **"Get started"** if not already enabled
5. Register your web app:
   - Click **"Add app"**
   - Select **"Web"**
   - Enter your app domain (e.g., `your-project.web.app`)

### 2. Enable reCAPTCHA v3

1. In App Check settings, choose **reCAPTCHA v3** as provider
2. Go to [Google reCAPTCHA Admin](https://www.google.com/recaptcha/admin)
3. Create a new site key:
   - **Type**: reCAPTCHA v3
   - **Domains**: Add your Firebase Hosting domain(s)
     - `${FIREBASE_PROJECT_ID}.web.app`
     - `${FIREBASE_PROJECT_ID}.firebaseapp.com`
     - `localhost` (for development)
4. Copy the **Site Key** (this is your `RECAPTCHA_SITE_KEY`)

### 3. Configure Environment Variables

#### Backend (.env file)
```bash
# Enable App Check in production
APP_CHECK_ENABLED=true

# Firebase Configuration
FIREBASE_PROJECT_ID=your-firebase-project-id

# Debug mode (use in development only)
APP_CHECK_DEBUG=false
```

#### Frontend (deploy-frontend.bat)
The frontend configuration is automatically injected during deployment via the `deploy-frontend.bat` script.

Ensure these variables are set in your `.env` file:
```bash
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_API_KEY=your-api-key
RECAPTCHA_SITE_KEY=6LeXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
APP_CHECK_ENABLED=true
```

### 4. Deploy

#### Backend
```powershell
cd translator-agent
.\build-backend.bat
.\deploy-backend.bat
```

#### Frontend
```powershell
.\deploy-frontend.bat
```

The deployment script will:
1. Read environment variables from `.env`
2. Inject them into `index.html`
3. Deploy to Firebase Hosting

### 5. Verify Setup

1. Open your deployed app in browser
2. Open DevTools Console
3. Look for messages:
   ```
   [App Check] Firebase initialized
   [App Check] Initialized with reCAPTCHA v3
   ```

4. Make an API call - you should see:
   ```
   Request Headers:
   X-Firebase-AppCheck: <token>
   ```

## Development Mode

During local development, you can disable App Check:

```bash
# .env
APP_CHECK_ENABLED=false
```

Or use debug tokens:
1. Enable debug mode: `APP_CHECK_DEBUG=true`
2. Check browser console for debug token
3. Add debug token in Firebase Console > App Check > Debug tokens

## Troubleshooting

### "App Check token required" error
- Verify `APP_CHECK_ENABLED=true` in backend `.env`
- Check that frontend has valid `RECAPTCHA_SITE_KEY`
- Verify reCAPTCHA domains include your app domain

### "Invalid App Check token" error
- Check that `FIREBASE_PROJECT_ID` matches in both backend and frontend
- Verify App Check is enabled in Firebase Console
- Check for clock skew issues

### reCAPTCHA not loading
- Verify `RECAPTCHA_SITE_KEY` is correct
- Check browser console for errors
- Ensure domain is whitelisted in reCAPTCHA admin

## Security Best Practices

1. **Always enable in production**: Set `APP_CHECK_ENABLED=true`
2. **Rotate reCAPTCHA keys**: Periodically regenerate keys
3. **Monitor App Check metrics**: Check Firebase Console for abuse
4. **Combine with rate limiting**: App Check + rate limits = better protection
5. **Use debug tokens carefully**: Never commit debug tokens to Git

## Protected Endpoints

The following endpoints require App Check tokens:
- `/api/translate` - Translation service
- `/api/tts` - Text-to-speech
- `/query` - General query endpoint

Exempt endpoints (no App Check required):
- `/api/config` - Configuration
- `/api/debug/*` - Debug endpoints
- `/health` - Health check

## Additional Resources

- [Firebase App Check Documentation](https://firebase.google.com/docs/app-check)
- [reCAPTCHA v3 Documentation](https://developers.google.com/recaptcha/docs/v3)
- [Cloud Run Security Best Practices](https://cloud.google.com/run/docs/securing/securing-services)
