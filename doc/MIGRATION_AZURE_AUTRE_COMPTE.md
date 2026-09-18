# Migration NutriFAQ vers un autre compte Azure

Ce guide decrit une migration complete de l'application NutriFAQ (backend + frontend) vers un autre tenant / abonnement Azure.

## 1. Objectif et perimetre

Ce document couvre:
- migration du backend FastAPI sur Azure App Service Linux
- migration du frontend statique sur Azure Storage Static Website
- configuration des variables d'environnement
- verification post-deploiement
- plan de rollback

Ce document s'appuie sur les scripts existants:
- `deploy-backend-azure.ps1`
- `deploy-frontend-azure.ps1`

## 2. Prerequis

1. Outils locaux
- Azure CLI installe (`az`)
- PowerShell 5.1+
- Python 3.11+
- Repository local a jour

2. Acces Azure
- droits Contributor (ou plus) sur le nouvel abonnement
- droits pour creer App Service Plan, Web App, Storage Account

3. Secrets et integrations
- cles API (OpenAI / Vercel / Azure OpenAI)
- eventuels secrets Entra ID
- acces au compte de stockage (si utilise)

4. Recommandation importante
- ne pas re-utiliser les secrets de production sans rotation
- preparer un fichier `.env` dedie au nouvel environnement

## 3. Se connecter au nouvel abonnement

1. Login Azure
```powershell
az login
```

2. Lister les abonnements disponibles
```powershell
az account list -o table
```

3. Selectionner le bon abonnement cible
```powershell
az account set --subscription "<SUBSCRIPTION_ID_OU_NOM>"
```

4. Verifier le contexte actif
```powershell
az account show -o table
```

## 4. Preparer la configuration locale (.env)

Mettre a jour `.env` avec les valeurs cible.

Variables minimales backend a verifier:
- `LLM_PROVIDER`
- `EMBEDDING_PROVIDER`
- `AI_GATEWAY_API_KEY` (si provider vercel)
- `AZURE_OPENAI_CHAT_ENDPOINT`
- `AZURE_OPENAI_CHAT_API_KEY`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_ENDPOINT`
- `AZURE_OPENAI_EMBEDDING_API_KEY`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_STORAGE_*`
- `AZURE_KB_BLOB_*`
- `DEMO_MODE`

Variable frontend utile:
- `BACKEND_URL`

## 5. Deployer le backend sur le nouveau compte

1. Lancer le script backend avec des noms explicites
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy-backend-azure.ps1 `
  -ResourceGroup "nutrifaq-rg" `
  -Location "canadacentral" `
  -PlanName "nutrifaq-plan-cc" `
  -AppName "nutrifaq-webapp" `
  -Sku "P0v3"
```

2. Si l'app doit etre reconstruite proprement
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy-backend-azure.ps1 `
  -ResourceGroup "nutrifaq-rg" `
  -Location "canadacentral" `
  -PlanName "nutrifaq-plan-cc" `
  -AppName "nutrifaq-webapp" `
  -ResetServer
```

3. Notes de fonctionnement du script
- le script cree/reutilise le Resource Group
- cree/reutilise le Plan App Service Linux
- cree/reutilise la Web App
- injecte les app settings depuis l'environnement/.env
- package puis deploye le backend
- verifie la presence des fichiers essentiels sur `/home/site/wwwroot`

## 6. Synchroniser les App Settings serveur avec .env

Appliquer explicitement les variables critiques (exemple):
```powershell
az webapp config appsettings set -g nutrifaq-rg -n nutrifaq-webapp --settings `
  BACKEND_URL="https://<ton-backend>.azurewebsites.net" `
  LLM_PROVIDER="vercel" `
  EMBEDDING_PROVIDER="vercel" `
  AZURE_OPENAI_CHAT_ENDPOINT="https://..." `
  AZURE_OPENAI_CHAT_DEPLOYMENT="..." `
  AZURE_OPENAI_EMBEDDING_ENDPOINT="https://..." `
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT="..." `
  DEMO_MODE="true"

az webapp restart -g nutrifaq-rg -n nutrifaq-webapp
```

Verifier ensuite:
```powershell
az webapp config appsettings list -g nutrifaq-rg -n nutrifaq-webapp --query "[?name=='BACKEND_URL' || name=='LLM_PROVIDER' || name=='EMBEDDING_PROVIDER' || name=='AZURE_OPENAI_CHAT_DEPLOYMENT' || name=='AZURE_OPENAI_EMBEDDING_DEPLOYMENT' || name=='DEMO_MODE'].{name:name,value:value}" -o table
```

## 7. Deployer le frontend sur le nouveau compte

1. Lancer le script frontend
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy-frontend-azure.ps1 `
  -ResourceGroup "nutrifaq-rg" `
  -Location "canadacentral" `
  -StorageAccountName "nutrifaqfeprod" `
  -FrontendDir "public" `
  -BackendUrl "https://<ton-backend>.azurewebsites.net" `
  -BackendAppName "nutrifaq-webapp" `
  -UpdateBackendCors
```

2. Ce que fait le script frontend
- cree/reutilise le storage account
- active static website
- injecte `backend-url.js`
- upload les assets dans `$web`
- optionnel: ajoute l'origine frontend dans CORS backend

## 8. Verifications post-migration

1. Sante backend
```powershell
Invoke-WebRequest "https://<ton-backend>.azurewebsites.net/health" -UseBasicParsing
```

2. Endpoint racine backend
```powershell
Invoke-WebRequest "https://<ton-backend>.azurewebsites.net/" -UseBasicParsing
```

3. Test fonctionnel query (local simple frontend)
- lancer `start-example-frontend.ps1`
- ouvrir `http://127.0.0.1:5501`
- envoyer une question

4. Verifier les logs de deploiement si echec
```powershell
az webapp log deployment list -g nutrifaq-rg -n nutrifaq-webapp -o table
az webapp log deployment show -g nutrifaq-rg -n nutrifaq-webapp --deployment-id <ID> -o json
```

## 9. Erreurs frequentes et corrections

1. Erreur `DeploymentNotFound` (Azure OpenAI)
Cause: nom de deployment chat/embedding incorrect.
Correction:
- verifier `AZURE_OPENAI_CHAT_DEPLOYMENT`
- verifier `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- redemarrer la Web App

2. Backend accessible mais query en erreur
Cause frequente: provider/cle incoherents.
Correction:
- aligner `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, cles associees
- verifier app settings serveur vs `.env`

3. OneDeploy failed status=3
Cause possible: echec post-build deploiement.
Correction:
- lire detail via `az webapp log deployment show`
- utiliser `-ResetServer` si necessaire

4. CORS frontend
Cause: origine frontend absente.
Correction:
- redeployer frontend avec `-UpdateBackendCors`
- verifier `ADDITIONAL_CORS_ORIGINS`

## 10. Rollback rapide

Option A: rollback configuration
1. restaurer anciennes app settings
2. redemarrer web app

Option B: rollback code
1. redeployer une ancienne version zip connue stable
2. verifier `/health` et un test query

Option C: rollback DNS/front
1. repointer la consommation frontend vers ancien backend

## 11. Check-list finale

- abonnement Azure cible selectionne
- backend deployee et `/health` OK
- app settings backend alignes avec `.env`
- frontend deployee et connecte au bon backend
- test query effectif OK
- CORS valide
- logs propres (pas d'erreur critique)

## 12. Commandes utiles

Afficher URL backend:
```powershell
az webapp show -g nutrifaq-rg -n nutrifaq-webapp --query defaultHostName -o tsv
```

Afficher URL frontend static website:
```powershell
az storage account show -g nutrifaq-rg -n nutrifaqfeprod --query primaryEndpoints.web -o tsv
```

Lister deployments backend:
```powershell
az webapp log deployment list -g nutrifaq-rg -n nutrifaq-webapp -o table
```

## 13. Donner les droits client a l'API (RBAC)

Objectif:
- un usager avec role `client` peut appeler `POST /query`
- les endpoints collaborator/admin doivent renvoyer `403`

### Etape 1 - Desactiver le mode demo

Si `DEMO_MODE=true`, les verifications de droits peuvent etre bypass.

```powershell
az webapp config appsettings set -g nutrifaq-rg -n nutrifaq-webapp --settings DEMO_MODE=false
az webapp restart -g nutrifaq-rg -n nutrifaq-webapp
```

### Etape 2 - Verifier le endpoint de gestion des roles

Les endpoints de role sont dans `api/routes/users.py` et exigent un token admin.

Exemples:
- `GET /api/users`
- `PUT /api/users/{user_object_id}/role`
- `DELETE /api/users/{user_object_id}/role`

### Etape 3 - Assigner le role client a un usager

Utiliser un token admin Entra ID:

```powershell
$api = "https://<ton-backend>.azurewebsites.net"
$adminToken = "<TOKEN_ADMIN>"
$userObjectId = "<OID_ENTRA_DU_CLIENT>"

Invoke-RestMethod -Method Put `
  -Uri "$api/api/users/$userObjectId/role" `
  -Headers @{ Authorization = "Bearer $adminToken" } `
  -ContentType "application/json" `
  -Body '{"role":"client"}'
```

### Etape 4 - Verification fonctionnelle des droits

Avec un token client:

1. Doit reussir
- `POST /query`

2. Doit etre refuse
- `GET /api/get_config` (403 attendu)
- `POST /api/database/regenerate` (403 attendu)
- `GET /api/blob/files` (403 attendu)

### Etape 5 - Audit des roles assignes

Avec un token admin:

```powershell
Invoke-RestMethod -Method Get `
  -Uri "https://<ton-backend>.azurewebsites.net/api/users" `
  -Headers @{ Authorization = "Bearer <TOKEN_ADMIN>" }
```

### Etape 6 - Option securite stricte (recommandee)

S'assurer que les utilisateurs non assignes n'obtiennent pas un role trop permissif par defaut.

Si necessaire:
- assigner explicitement `client` a tous les usagers standards
- ou modifier le role par defaut dans `api/services/entra_auth_service.py`
