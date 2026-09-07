# Setup and execution

This guide runs the local prototype from a clean checkout.

## Prerequisites

- Windows, macOS, or Linux
- Python 3.10 or newer
- Node.js 18 or newer
- An OpenAI API key for the triage and Q&A calls

## In Short

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

```
cd frontend
npm install
npm run dev
```
Frontend must be served in port 5173, or change port number in main.py

langfuse dashboard API must be provided (Updated) to view it from your own account dashboard.

Press x500 speed for faster demo

## Backend

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

On macOS or Linux, use `source .venv/bin/activate` instead.


I have included a .env file with already existing API key with a few $ credits which can be used.

(or)


Create `backend/.env` locally by copying `backend/.env.example`:

```text
OPENAI_API_KEY=replace-with-a-local-key
ENVIRONMENT=development
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# DATA_ENCRYPTION_KEY=replace-with-a-fernet-key
# Optional for local development; set this to enable bearer authentication.
# AUTH_TOKEN=replace-with-a-long-random-token
# AUTH_USER_ID=demo-handler
# AUTH_ROLE=handler
# AUTH_HANDLER_TYPES=Claims,Motor,Home,Liability,Finance
# AUTH_USERS_JSON=[{"token":"local-secret","user_id":"home-handler-1","role":"handler","handler_types":["Home"]}]
# RETENTION_DAYS=365
# LANGFUSE_PUBLIC_KEY=replace-with-langfuse-public-key
# LANGFUSE_SECRET_KEY=replace-with-langfuse-secret-key
# LANGFUSE_HOST=https://cloud.langfuse.com
```

The complete backend dependency list is maintained in [requirements.txt](../backend/requirements.txt).

Do not commit this file or place a real key in documentation.

With `ENVIRONMENT=development` and no `AUTH_TOKEN`, local requests use the demo handler context. When `AUTH_TOKEN` is configured, REST requests must include `Authorization: Bearer <token>` and the dashboard WebSocket must receive the same bearer credential.

## Authentication and sessions

In development, the browser presents a login screen with seeded demo users. Login creates an HttpOnly `triage_session` cookie. The session is held in backend memory and expires after eight hours; restarting the backend logs users out.

For production-style token authentication, set `ENVIRONMENT=production` and configure either `AUTH_TOKEN` or `AUTH_USERS_JSON`. Do not use the seeded passwords outside local evaluation.

Start the backend from the `backend` directory:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

The API is available at `http://localhost:8000`. FastAPI's interactive API page is at `http://localhost:8000/docs`.

## Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo users

In development, the login screen loads these seeded accounts and fills their passwords automatically:

| Username | Password | Role | Departments |
| --- | --- | --- | --- |
| `claims.handler` | `claims-demo` | handler | Claims |
| `home.handler` | `home-demo` | handler | Home |
| `motor.handler` | `motor-demo` | handler | Motor |
| `operations.supervisor` | `supervisor-demo` | supervisor | All departments |
| `audit.user` | `audit-demo` | auditor | All departments, read-only |

These credentials exist only for local demonstration. Replace them with IAM/OIDC-backed identity before deployment.

Useful checks:

```powershell
npm run build
npm run lint
```

## First run

1. Start the backend.
2. Start the frontend.
3. Open the dashboard.
4. Click `Play Stream`.
5. Select a department from the handler selector. The selector changes the view; it does not control ingestion.
6. Open a thread to inspect actions, rationale, confidence, audit history, notes, drafts, and Q&A.

The simulator starts paused. Playback speed controls how quickly the sample timeline is processed.

## Resetting local state

Stop the backend first. From the project root:

```powershell
Remove-Item .\backend\triage_state.db -ErrorAction SilentlyContinue
```

If the terminal is already in `backend`, use:

```powershell
Remove-Item .\triage_state.db -ErrorAction SilentlyContinue
```

The database contains generated thread state, source messages, audit events, notes, action changes, and reply drafts. The sample input remains in `backend/data/emails_candidate.json`.

## Evaluation

Run the focused backend tests with:

```powershell
..\.venv\Scripts\python.exe -m pytest backend\tests -q
```

After the simulator has processed the relevant threads:

```powershell
.\.venv\Scripts\python.exe .\backend\evaluate.py
```

Results are written to `artifacts/eval_results/triage_evaluation.json`.