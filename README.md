# Niyam AI Regulatory Change Intelligence

An initial full-stack implementation for Indian SME regulatory document ingestion, version history, PDF text comparison, profile context, action tracking, and evidence-oriented reports, with React/Vite frontend and FastAPI backend.

## Current scope and important limitations

- The configured demonstration source was inspected live. It exposes `GET /api/v1/public-regulations?limit=100&offset=0`, with pagination, regulation/version IDs, metadata, SHA-256 values, and public-document routes that redirect to short-lived signed Supabase links. The current catalog exposed two distinct version-1 records, not an established old/new revision pair.
- The source adapter follows pagination, validates approved HTTPS hosts across redirects, checks PDF signatures, size, and advertised content hash, stores each version separately, and extracts selectable text. One failed source record is persisted with an error for retry.
- The comparison uses normalized extracted text and Python `SequenceMatcher`; changes preserve original text and page references. It does not yet implement robust legal-clause alignment, table reconstruction, OCR, or a legal-equivalence determination. Each textual difference is marked for review.
- Change-level analysis now stores individual findings, profile characteristics, clause scope conditions, missing facts/questions, recommendations, priority rationale, source-page evidence, and review state. Deterministic rules can classify explicit universal scope, profile industry mentions, registration references, and numeric employee scope conditions. Other ambiguous cases remain `NEEDS_VERIFICATION`; this rule set is not a complete legal ontology.
- Applicability outcomes are per finding. A regulation-level overall label is intentionally not inferred from mixed clause results. Text matches and deterministic scope conditions are decision-support signals and need professional review.
- Optional Gemini interpretation is enabled with `GEMINI_API_KEY`. Results are treated as suggestions. A deadline is retained only if its ISO date and supporting text are explicitly present in the clause. Without the key, text comparison remains available and interpretation is clearly labeled unconfigured.
- Authentication uses random opaque server-side sessions, hashed in the database, with an HTTP-only cookie. Public signup always creates a `user`. Admin bootstrap promotes only an existing account matching `ADMIN_BOOTSTRAP_EMAIL` and requires `ADMIN_BOOTSTRAP_SECRET`. This local prototype does not yet provide tenant-level ownership isolation, CSRF tokens, rate limiting, full audit logging, OCR, or object-storage support; it is not production-ready. Use HTTPS, set `COOKIE_SECURE=true`, managed PostgreSQL and durable object storage before deployment.
- The additive impact-analysis schema migration is in `backend/app/migrations.py`. New installations still initialize metadata at API startup. Existing installations can run `python -c "from backend.app.database import engine; from backend.app.migrations import upgrade; upgrade(engine)"`; downgrade drops only the new analysis tables and therefore discards their data.
- The API's built-in scheduler is appropriate for a single persistent local API process. For deployments, run the independent worker below and set `SYNC_ENABLED=false` on the API. Keep exactly one worker replica until a database-backed distributed lock is implemented. Serverless runtimes are not suitable for this polling worker.

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- A persistent filesystem for local SQLite and PDFs

## Local development

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m pip install pytest
npm --prefix frontend install
```

Initialize the database (also done automatically on API startup):

```powershell
python -c "from backend.app.database import Base, engine; import backend.app.models; Base.metadata.create_all(engine)"
python -c "from backend.app.database import engine; from backend.app.migrations import upgrade; upgrade(engine)"
```

Run the API and frontend in separate terminals:

```powershell
python -m uvicorn backend.app.main:app --reload --port 8000
npm --prefix frontend run dev
```

Run an independent scheduler worker instead of API-process scheduling:

```powershell
$env:SYNC_ENABLED = "false"
python -m uvicorn backend.app.main:app --reload --port 8000
python -m backend.app.worker
```

Open the frontend at `http://localhost:5173`, API explorer at `http://localhost:8000/docs`; routes are `/`, `/signup`, `/signin`, `/app`, `/admin/login`, and `/admin`. Trigger the first source sync using **Sync now**. Scheduled synchronization defaults to five minutes and is configurable with `SYNC_INTERVAL_MINUTES`.

## Environment

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///D:/final/data/niam.db` |
| `DATA_DIR` | Local PDF and SQLite storage root | `D:/final/data` |
| `REGULATORY_SOURCE_URL` | Source portal listing page | Supplied portal URL |
| `SYNC_INTERVAL_MINUTES` | Scheduler interval, minimum one minute | `5` |
| `SYNC_ENABLED` | API scheduler on/off | `true` |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:5173` |
| `VITE_API_BASE_URL` | API origin embedded in frontend build (local Vite uses a same-origin proxy) | blank locally; configure for deployment |
| `GEMINI_API_KEY` | Optional Gemini interpretation key | unset |
| `MAX_PDF_BYTES` | Maximum source PDF download size | `26214400` |
| `COOKIE_SECURE` | Require HTTPS for session cookie | `false` locally; `true` in production |
| `COOKIE_SAMESITE` | Cookie same-site policy | `lax` locally/same-site; use `none` with HTTPS for cross-site frontend/API hosts |
| `ADMIN_BOOTSTRAP_EMAIL` | Registered account to promote to admin | unset |
| `ADMIN_BOOTSTRAP_SECRET` | Secret required by admin bootstrap endpoint | unset |

Never commit `.env` or secrets. Copy `.env.example` to `.env` in `D:\final`. The backend loads this file on startup. The database, uploads, and reports resolve to `D:\final\data`. Set the intended `ADMIN_BOOTSTRAP_EMAIL` in `.env`, register that exact email at `/signup`, then run `python -m backend.app.bootstrap_admin` from `D:\final`. This explicit local command only promotes the already registered configured account; it never creates credentials. The optional `/api/admin/bootstrap` API additionally requires `ADMIN_BOOTSTRAP_SECRET` in its JSON body. Remove or rotate that secret after setup. `DATABASE_URL` can point to PostgreSQL; install a PostgreSQL driver such as `psycopg[binary]` when deploying that configuration.

## API overview

All routes are under `/api`; interactive schemas are available at `/docs`. In local development, Vite proxies `/api` to port 8000 so session cookies stay same-origin.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health |
| `POST` | `/auth/register` | Register user and start session |
| `POST` | `/auth/login` | Sign in and start session |
| `GET` | `/auth/me` | Restore current session |
| `POST` | `/auth/logout` | Revoke current session |
| `GET` | `/admin/users` | Admin-only bounded user list and count |
| `POST` | `/admin/bootstrap` | Promote configured existing account with bootstrap secret |

All regulatory workspace APIs require a signed-in session. The health endpoint and register/login/logout endpoints are public; admin APIs require the `admin` role.
| `GET` | `/sources` | Configured source and connection summary |
| `POST` | `/sources/sync` | Queue a source synchronization |
| `GET` | `/sources/sync/status` | Current and latest run status |
| `PUT` | `/sources/sync/settings` | Enable/disable API scheduler |
| `GET` | `/sources/sync/history` | Recent run counters and errors |
| `GET` | `/dashboard/metrics` | Persisted record, finding, action, failure, and date-filtered metrics |
| `GET` | `/regulations` | Searchable, paginated stored documents |
| `GET` | `/regulations/{id}` | Document metadata, extracted text, and versions |
| `GET` | `/regulations/{id}/versions` | Version history |
| `POST` | `/regulations/{id}/retry` | Retry source synchronization for failed item |
| `GET` | `/regulations/{id}/download` | Download stored PDF |
| `GET`, `POST` | `/business-profiles` | List/create business profiles |
| `PUT`, `DELETE` | `/business-profiles/{id}` | Update/delete profile |
| `POST` | `/documents/upload` | Compare uploaded old and new PDFs |
| `POST` | `/documents/compare` | Compare stored document IDs |
| `POST` | `/regulations/{id}/analyze` | Assess current-version clauses against a profile without claiming a historical comparison |
| `GET` | `/impact-analysis` | List analyses |
| `GET` | `/impact-analysis/{id}` | Retrieve evidence report |
| `PATCH` | `/impact-analysis/{id}/findings/{change_id}/review` | Persist reviewer state and regenerate saved PDF |
| `GET` | `/impact-analysis/{id}/evidence/{role}/download` | Open stored source PDF for citation review |
| `GET` | `/actions` | List/filter compliance actions |
| `PATCH` | `/actions/{id}` | Update action status |
| `GET` | `/reports/{id}` | Retrieve report |
| `GET` | `/reports` | Search saved reports |
| `GET` | `/reports/{id}/download` | Download report PDF |

## Tests and builds

```powershell
python -m pytest backend\tests -q
npm --prefix frontend run build
```

The tests use synthetic PDFs and stubbed source API responses; they do not claim the demo source has a real amendment pair. Perform an explicit source sync against the live portal for an integration check.

## Deployment

### Frontend on Vercel

The root `vercel.json` configures Vite output in `frontend/dist`. Configure `VITE_API_BASE_URL` to the deployed persistent API and set that frontend origin in the backend's `CORS_ORIGINS`. Vercel hosts only the static frontend; it does not run the long-lived scheduler.

### Persistent API and worker

Deploy `backend/requirements.txt` and the repository to a persistent Python host. Start the API with:

```sh
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Start exactly one separate worker process with:

```sh
python -m backend.app.worker
```

Set `SYNC_ENABLED=false` on the API when the worker owns scheduling, and configure the worker's `SYNC_INTERVAL_MINUTES`. Use a managed PostgreSQL database and durable object storage before multiple replicas or ephemeral deployment storage. Configure HTTPS, restrictive CORS, authentication/tenant ownership, request rate limits, backups, monitoring, and database migrations before public production use.

## Troubleshooting

- **No documents visible:** start the API, open `/docs`, and `POST /api/sources/sync`; inspect sync history for source/API errors.
- **A PDF failed:** inspect its persisted `FAILED` state and error, then use the document retry control/API after resolving the cause.
- **Scanned PDF:** selectable text is absent; configure an OCR engine before relying on that document. Current behavior reports the limitation.
- **No legal applicability result:** the application conservatively requests verification; it does not equate keyword overlap with legal applicability.
- **Frontend API unavailable:** set `VITE_API_BASE_URL` at build time and allow the frontend origin in backend `CORS_ORIGINS`.

## Hackathon project report

See [PROJECT_REPORT.md](PROJECT_REPORT.md) for the project overview, architecture, implemented features, verification results, limitations, and final submission checklist. Team details and sanitized product screenshots still need to be added.

## Publish this project to GitHub

The repository intentionally excludes `.env` files, the SQLite database and uploaded data, Python virtual environments, installed Node dependencies, and generated build output. Commit `.env.example` only; it contains placeholders. Do not force-add ignored files.

From the VS Code PowerShell terminal in `D:\final`, initialize and inspect the local repository, then commit:

```powershell
git init -b main
git add .
git status --short
git commit -m "Initial Niyam AI application"
```

After creating an empty GitHub repository, connect it and push the `main` branch:

```powershell
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

Replace the remote URL with the URL copied from your GitHub repository. Authenticate through the Git Credential Manager prompt or GitHub CLI; never put a personal access token in the remote URL.
