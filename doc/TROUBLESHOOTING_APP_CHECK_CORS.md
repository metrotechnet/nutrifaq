# Nutria Agent – Documentation
# 🚨 Dépannage: Erreur CORS Firebase App Check

Ce document explique comment diagnostiquer et résoudre les problèmes de CORS liés à Firebase App Check pour le projet **Nutria Agent**. Suivez ces étapes pour garantir une configuration correcte lors du déploiement ou du développement.

## Problème
```
Access to fetch at 'https://content-firebaseappcheck.googleapis.com/...'
from origin 'https://imx-translator.web.app' has been blocked by CORS policy
```

## Cause
Le domaine `imx-translator.web.app` n'est pas enregistré comme application web autorisée dans Firebase Console.

## ✅ Solution étape par étape

### 1. Enregistrer l'application web dans Firebase

1. **Aller à Firebase Console:**
   - https://console.firebase.google.com/
   - Sélectionnez projet: `imx-translator`

2. **Ajouter une application web:**
   - Cliquez sur l'icône **</>** (Web) dans la page d'accueil
   - OU allez dans **Project Settings** > **General** > **Your apps**
   - Cliquez **"Add app"** > **Web**
   
3. **Configurer l'app:**
   - **App nickname**: IMX Translator (ou autre nom)
   - **Firebase Hosting**: ✅ Cochez cette option
   - **Choose site**: Sélectionnez `imx-translator`
   - Cliquez **"Register app"**

4. **Copier la configuration:**
   ```javascript
   const firebaseConfig = {
     apiKey: "AIzaSyCa9xbAeLgwOula7_zxQwKjvshTrKIOTWQ",
     authDomain: "imx-translator.firebaseapp.com",
     projectId: "imx-translator",
     storageBucket: "imx-translator.appspot.com",
     messagingSenderId: "...",
     appId: "..."
   };
   ```
   
   ⚠️ Notez le **appId** - vous en aurez besoin!

### 2. Activer App Check pour cette app

1. **Dans Firebase Console:**
   - Allez à **Project Settings** > **App Check**
   - Si pas encore activé, cliquez **"Get started"**

2. **Configurer reCAPTCHA v3:**
   - Sous votre app web, cliquez **"⋮"** > **Edit**
   - Provider: **reCAPTCHA v3**
   - Site key: `6Lf_H3ksAAAAAKOeJrorLgPS8XEJJEP4OEwH2P1U`
   - Cliquez **"Save"**

### 3. Vérifier les domaines reCAPTCHA

1. **Aller à reCAPTCHA Admin:**
   - https://www.google.com/recaptcha/admin
   - Sélectionnez votre site avec la clé: `6Lf_H3ksAAAAAKOeJrorLgPS8XEJJEP4OEwH2P1U`

2. **Vérifier les domaines:**
   - **Domaines autorisés** doit inclure:
     ```
     imx-translator.web.app
     imx-translator.firebaseapp.com
     localhost
     ```
   
3. **Si domaines manquants:**
   - Cliquez **Settings**
   - Ajoutez les domaines manquants
   - Sauvegardez

### 4. Mettre à jour .env avec l'App ID

Ajoutez dans votre `.env`:
```bash
FIREBASE_APP_ID=1:XXXXXXXXX:web:YYYYYYYY
FIREBASE_MESSAGING_SENDER_ID=XXXXXXXXX
```

### 5. Redéployer le frontend

```powershell
cd translator-agent
.\deploy-frontend.bat
```

### 6. Attendre 5 minutes

Firebase App Check peut prendre quelques minutes pour propager les changements.

---

## 🔄 Solution temporaire: Désactiver App Check

Si vous devez déployer rapidement en attendant la configuration:

**Dans `.env`:**
```bash
# Désactiver temporairement App Check
APP_CHECK_ENABLED=false
```

**Redéployer:**
```powershell
.\build-backend.bat
.\deploy-backend.bat
.\deploy-frontend.bat
```

⚠️ **N'oubliez pas de réactiver en production!**

---

## ✅ Vérification

Une fois configuré, ouvrez https://imx-translator.web.app et vérifiez la console (F12):

**Messages attendus:**
```
[App Check] Firebase initialized
[App Check] Initialized with reCAPTCHA v3
```

**Pas d'erreurs CORS!**

---

## 🐛 Autres problèmes possibles

### Erreur: "reCAPTCHA placeholder element must be an element or id"

**Solution:** Le site key reCAPTCHA est invalide ou le domaine n'est pas autorisé.

### Erreur: "App Check token expired"

**Solution:** Normale - les tokens expirent. App Check les rafraîchit automatiquement.

### Erreur: "Invalid App Check token"

**Causes possibles:**
- `FIREBASE_PROJECT_ID` différent entre frontend et backend
- App Check pas activé dans Firebase Console
- Token expiré (vérifier l'horloge système)

---

## 📞 Support

Si le problème persiste:
1. Vérifiez les logs Firebase Console > App Check
2. Testez avec `APP_CHECK_DEBUG=true` pour voir les tokens
3. Utilisez un debug token pour tester localement

## 🔗 Liens utiles

- [Firebase Console - App Check](https://console.firebase.google.com/project/imx-translator/appcheck)
- [reCAPTCHA Admin](https://www.google.com/recaptcha/admin)
- [Firebase App Check Docs](https://firebase.google.com/docs/app-check/web/recaptcha-provider)
