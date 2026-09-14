# Nutria Agent – Documentation
# 🛷 Guide: Tester avec un Debug Token Firebase

Ce guide explique comment utiliser un debug token Firebase App Check pour le projet **Nutria Agent**. Il est destiné au développement local, aux tests automatisés et au débogage.

## Qu'est-ce qu'un Debug Token?

Un debug token permet de tester Firebase App Check sans reCAPTCHA. Idéal pour:
- Développement local
- Tests automatisés
- Environnements CI/CD
- Debugging

## 📋 Étapes de configuration

### 1. Enregistrer le debug token dans Firebase Console

1. **Aller à Firebase Console:**
   ```
   https://console.firebase.google.com/project/imx-translator/appcheck
   ```

2. **Naviguer vers App Check:**
   - Project Settings > App Check
   - Cliquez sur **"Manage debug tokens"**

3. **Ajouter le token:**
   - Cliquez **"Add debug token"**
   - Collez votre debug token
   - Donnez un nom descriptif (ex: "Local Dev - [Votre Nom]")
   - Cliquez **"Save"**

### 2. Configurer votre environnement local

**Ajoutez dans votre `.env`:**
```bash
# Firebase App Check
APP_CHECK_ENABLED=true
FIREBASE_PROJECT_ID=imx-translator
FIREBASE_API_KEY=AIzaSyCa9xbAeLgwOula7_zxQwKjvshTrKIOTWQ

# Debug Token pour développement local
APP_CHECK_DEBUG_TOKEN=VOTRE_DEBUG_TOKEN_ICI
```

**Exemple complet:**
```bash
APP_CHECK_DEBUG_TOKEN=1234abcd-5678-efgh-90ij-klmnopqrstuv
```

### 3. Redémarrer le backend (si nécessaire)

```powershell
cd translator-agent
.\start-backend.ps1
```

Le backend n'a pas besoin d'être modifié - il accepte les debug tokens automatiquement via Firebase Admin SDK.

### 4. Tester localement

#### Option A: Avec le serveur de développement local

**Ouvrez dans le navigateur:**
```
http://localhost:3000
```

**Vérifiez la console (F12):**
```
[App Check] Firebase initialized
[App Check] Debug mode enabled with token: 1234abcd-5678-efgh...
[App Check] Initialized with debug token
```

**Faites une traduction:**
- Entrez du texte
- Cliquez "Traduire"
- Vérifiez F12 > Network
- L'en-tête doit contenir: `X-Firebase-AppCheck: [votre-debug-token]`

#### Option B: Déployer avec debug token

```powershell
.\deploy-frontend.bat
```

Le token sera injecté dans le HTML déployé.

⚠️ **IMPORTANT:** Ne déployez PAS en production avec un debug token! Utilisez reCAPTCHA en production.

### 5. Vérification complète

**Test 1: API health check**
```powershell
curl http://localhost:8080/health
```
✅ Devrait retourner: `{"status":"ok"}`

**Test 2: API protégée avec debug token**

Faites une traduction dans l'interface web et vérifiez:
1. Console navigateur: `[App Check] Initialized with debug token`
2. Network tab: Header `X-Firebase-AppCheck` présent
3. Backend logs: `[App Check] App Check token verified`

**Test 3: API protégée SANS token (simulation attaque)**
```powershell
curl -X POST http://localhost:8080/api/translate `
  -H "Content-Type: application/json" `
  -d '{"text":"Hello","target_language":"fr","source_language":"en"}'
```
❌ Devrait retourner: `401 Unauthorized`

## 🐛 Dépannage

### Erreur: "Invalid App Check token"

**Causes:**
- Debug token pas enregistré dans Firebase Console
- Typo dans le token
- Token expiré ou révoqué

**Solution:**
1. Vérifiez Firebase Console > App Check > Debug tokens
2. Vérifiez le token dans `.env` (pas de guillemets, pas d'espaces)
3. Redéployez: `.\deploy-frontend.bat`

### Erreur: "App Check token required"

**Causes:**
- Backend n'a pas `APP_CHECK_ENABLED=true`
- Frontend n'envoie pas le token

**Solution:**
1. Vérifiez `.env` backend: `APP_CHECK_ENABLED=true`
2. Redémarrez le backend
3. Vérifiez console navigateur pour messages App Check

### Le debug token n'apparaît pas dans les headers

**Solution:**
1. Videz le cache navigateur (Ctrl+Shift+R)
2. Vérifiez `window.APP_CHECK_DEBUG_TOKEN` dans console navigateur
3. Redéployez: `.\deploy-frontend.bat`

## 📊 Comportement attendu

| Scénario | Résultat |
|----------|----------|
| Frontend local avec debug token | ✅ 200 OK |
| Postman/curl sans token | ❌ 401 Unauthorized |
| Postman/curl avec debug token header | ✅ 200 OK |
| Frontend production avec reCAPTCHA | ✅ 200 OK |
| Frontend production avec debug token | ❌ Ne pas utiliser! |

## 🔒 Sécurité

### ⚠️ Points importants:

1. **NE PAS commiter le debug token dans Git**
   - Ajoutez `.env` dans `.gitignore`
   - Utilisez `.env.example` pour documenter

2. **NE PAS déployer en production avec debug token**
   - Avant déploiement production, commentez:
     ```bash
     # APP_CHECK_DEBUG_TOKEN=...
     ```
   - Laissez seulement `RECAPTCHA_SITE_KEY`

3. **Révoquer les tokens inutilisés**
   - Firebase Console > App Check > Debug tokens
   - Supprimez les anciens tokens

## 🚀 Workflow recommandé

**Développement local:**
```bash
# .env
APP_CHECK_ENABLED=true
APP_CHECK_DEBUG_TOKEN=your-debug-token
# RECAPTCHA_SITE_KEY=  # Commenté en local
```

**Production:**
```bash
# .env
APP_CHECK_ENABLED=true
# APP_CHECK_DEBUG_TOKEN=  # Commenté en production
RECAPTCHA_SITE_KEY=your-recaptcha-key
```

## 📞 Support

**Obtenir un nouveau debug token:**
1. Ouvrez l'app avec `APP_CHECK_ENABLED=true` mais sans `RECAPTCHA_SITE_KEY`
2. Console navigateur affichera: "DEBUG TOKEN: [nouveau-token]"
3. Copiez ce token
4. Ajoutez-le dans Firebase Console

**Liens utiles:**
- [Firebase App Check Debug Tokens](https://firebase.google.com/docs/app-check/web/debug-provider)
- [Firebase Console - App Check](https://console.firebase.google.com/project/imx-translator/appcheck)
