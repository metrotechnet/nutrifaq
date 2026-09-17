# Deploy API and Frontend

## 1. Create the Azure App Service for the API

Create a new **Web App** in Azure with these settings:

- Resource group: `nutrifaq-rg` (create it if it does not exist)
- App name: `nutrifaq-api`
- Runtime stack: `Python 3.11`
- Region: `Canada East`
- Pricing tier (SKU/size): `PremiumV3 P0V3`

## 2. Build the backend zip package

Create a zip package that includes only the required backend files.

- `include = {"app.py", "__init__.py", "requirements.txt", "startup.sh"}`
- `include_dirs = {"api", "nutrifaq-dbase"}`

## 3. Deploy the zip package to the Web App

Upload and deploy the zip package to the App Service.

## 4. Verify deployed files on the server

After deployment, confirm that required files are present under:

- `/home/site/wwwroot`

Expected entries:

- `app.py`
- `__init__.py`
- `requirements.txt`
- `startup.sh`
- `api/`
- `nutrifaq-dbase/`

## 5. Validate that the API is running

Check that the API is online by calling the health endpoint:

- `https://<your-api-host>/health`

A successful response should return HTTP `200`.

## 6. Get the API URL and update frontend deployment script

Copy the deployed API URL and set it in:

- `deploy-frontend-azure.ps1`

## 7. Deploy the frontend

Run frontend deployment using:

- `deploy-frontend-azure.ps1`
