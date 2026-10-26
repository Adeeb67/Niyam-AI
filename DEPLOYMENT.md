# Niyam AI deployment guide

This project has a Vite frontend and a FastAPI backend. The recommended first deployment is a Vercel frontend plus a separately hosted API. Keep the application database and uploaded PDFs on durable services; a Vercel function's local filesystem is not persistent storage.

## Before deploying

1. Push the latest code to the public GitHub repository.
2. In VS Code Explorer, locate the `package.json` used by the web client and note its containing directory. This is the Vercel **Root Directory**.
3. Locate the backend `requirements.txt` and the Python module that defines the FastAPI `app`. Note both paths for the Render service configuration.
4. Search the frontend for `localhost`, `127.0.0.1`, `VITE_`, and the API base URL. Production browser requests must use the public API URL, not localhost.
5. Identify every required backend environment variable from the backend settings and any `.env.example` file. Do not commit `.env` files or secrets.
6. Decide on durable production database and file storage. SQLite and local uploads are suitable for local development, but hosted services may have ephemeral filesystems. Use managed PostgreSQL and object storage, or explicitly configure persistent storage and verify it survives redeploys.
7. Configure the source-monitoring scheduler as a separate worker/cron process if it currently runs inside the API process. A serverless API should not rely on an always-running in-process scheduler.

## Deploy the API (Render)

1. Create a Render **Web Service** from the GitHub repository.
2. Set **Root Directory** to the backend directory containing `requirements.txt`.
3. Select Python. Set the build command to `pip install -r requirements.txt`.
4. Set the start command using the actual module path for the FastAPI app. For example, if the app is `app` inside `main.py`, use `uvicorn main:app --host 0.0.0.0 --port $PORT`. For a package, include it (for example `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`).
5. Add production environment variables in Render's dashboard. Set a strong secret, production database URL, storage credentials, allowed frontend origins, and any AI provider key if enabled. Never expose backend secrets as Vite variables.
6. Deploy. Open the service's health endpoint and API docs (`/docs`) to confirm it starts. Copy the service's HTTPS URL.
7. Check Render logs for database migration/startup errors and confirm the database and document storage use durable services.

## Deploy the frontend (Vercel)

1. Import the GitHub repository into Vercel.
2. Set **Root Directory** to the frontend directory found above (the directory containing its `package.json`).
3. Select Vite. Typical settings are build command `npm run build` and output directory `dist`; keep the package manager and build script consistent with the lockfile and `package.json`.
4. Add the frontend's existing API URL variable in Vercel Project Settings → Environment Variables. Use the exact variable name the frontend code reads (often `VITE_API_URL`) and set its value to the Render HTTPS API URL, including any required `/api` prefix. Vite-prefixed values are public in the browser; put no secrets there.
5. Deploy and copy the Vercel HTTPS domain.
6. Add that exact domain to the backend's allowed CORS origins. For cookie authentication across the two domains, configure credentialed CORS and secure cross-site cookies; do not use wildcard origins with credentials.
7. Redeploy the API after changing CORS, then redeploy the frontend after changing its environment variables. Vercel applies environment changes to new deployments.

## Verify production

From the deployed site, test account creation, login, session refresh, logout, and administrator authorization. Also test profile create/edit, document listing/download, PDF upload and comparison, saved reports, and source sync. In browser developer tools, inspect failed Network requests and CORS errors. Check API and worker logs. Verify uploaded files and database records remain after a redeploy before using real data.

## Hosting the API on Vercel instead

Vercel supports FastAPI/Python functions, but this project must first be checked and adapted for serverless operation: use external durable database and file storage, move scheduled polling out of the API process, and confirm every endpoint and dependency fits Vercel function limits. Do not deploy the current SQLite/local-file/in-process-scheduler setup as if it were production durable.

## VS Code terminal commands

Run these from `D:\final` after editing and reviewing the deployment settings:

```powershell
git status
git add DEPLOYMENT.md
git commit -m "Add deployment guide"
git push origin main
```

