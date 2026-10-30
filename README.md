# ControlIQ

**Continuous Technology Controls Monitoring & Risk Intelligence Platform**, demonstrated against
**Alpha Beta Bank**, a fictional organisation.

ControlIQ ingests control evidence, evaluates technology controls with deterministic and versioned
rules, stores every assessment as an immutable and reproducible record, and turns control failures into
explainable, risk-scored findings. Each finding is traced to the assets and business services it could
affect, and can only be closed by evidence-based revalidation.

> **Synthetic data only.** Every organisation, person, system, vulnerability and figure is fictional.
> No real bank or customer data is used, and no third-party branding appears.
>
> **No compliance claim.** ControlIQ implements common application-security controls. It is **not**
> represented as compliant with any banking regulation or standard. See [docs/SECURITY.md](docs/SECURITY.md)
> for the demo controls and the production-hardening gap.

## Modules

| Module | What it does |
| --- | --- |
| Executive Overview | Control effectiveness, Critical and overdue findings, services at potential exposure, 90-day trend, executive summary |
| Control Monitoring | 10 controls across 8 domains, per-asset status, rule definitions and parameters, assessment history, on-demand runs |
| Assessments | Immutable assessment records with input hash, evidence link and **Replay & verify** |
| Technology Assets | Inventory with criticality, exposure and redundancy; create and edit (Risk Analyst and Administrator) |
| Business Services | React Flow dependency map, impact tracing, single points of failure |
| Risk Register | Risks with inherent and residual ratings, treatment, and traceability to controls, findings and services |
| Findings & Remediation | Scored findings, workflow, remediation actions, time-bound risk acceptance, evidence-based validation |
| Evidence Center | Upload (JSON, CSV, PDF, TXT, LOG), schema validation, SHA-256 integrity, sample templates |
| Risk Intelligence | Grounded Q&A over platform records: rule-based by default, optional LLM |
| Reports | Five report types with preview and PDF export |
| Settings | Demo scenarios and reset, scoring weights, validation workflow, users and roles, audit log |

## Stack

- **Frontend:** Next.js 15 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui (Base UI), Lucide,
  Recharts, React Flow (`@xyflow/react`) with dagre layout, TanStack Query and TanStack Table, Vitest
- **Backend:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, Argon2, ReportLab, pytest
- **Database:** PostgreSQL 16
- **AI (optional):** any OpenAI-compatible chat-completions API. Without a key the assistant uses
  clearly labelled rule-based intelligence.

## Repository layout

```
backend/            FastAPI app (app/), Alembic migrations, pytest suite (tests/)
frontend/           Next.js app (src/app, src/components, src/lib)
scripts/            seed_demo.py (reset + seed), docker/init-test-db.sql
docs/               ARCHITECTURE, DATA_MODEL, RISK_SCORING, SECURITY, DEMO_GUIDE
docker-compose.yml  PostgreSQL 16 for local development
```

## Running locally

Prerequisites: **Python 3.12+** (developed on 3.13), **Node.js 20+** (developed on 22) and
**PostgreSQL 16**. You can run PostgreSQL with Docker or use an existing local instance.

### 1. Start PostgreSQL

**Option A — Docker Compose**

```bash
docker compose up -d
```

This creates the `controliq` user (password `controliq`) with the databases `controliq` and
`controliq_test`.

**Option B — an existing PostgreSQL 16**

Create the same role and databases yourself:

```sql
CREATE ROLE controliq LOGIN PASSWORD 'controliq';
CREATE DATABASE controliq OWNER controliq;
CREATE DATABASE controliq_test OWNER controliq;
```

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
Copy-Item .env.example .env           # macOS/Linux: cp .env.example .env
# Edit .env and set SECRET_KEY:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
alembic upgrade head                  # creates schema, constraints and the immutability triggers
cd ..
python scripts/seed_demo.py           # synthetic dataset + 90-day assessment history
cd backend
uvicorn app.main:app --port 8000 --reload
```

On Windows, set `$env:PYTHONIOENCODING = "utf-8"` before seeding if your console code page cannot print
non-ASCII characters.

API documentation: <http://localhost:8000/api/docs> · Health check: <http://localhost:8000/api/health>

### 3. Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local     # CONTROLIQ_API_URL=http://localhost:8000
npm run dev                           # http://localhost:3000
```

For a production build: `npm run build` then `npm run start`.

The browser talks only to the Next.js origin. `/api/*` is proxied to the FastAPI backend, so the session
cookie stays first-party.

### Demo accounts

All demo accounts use the password `ControlIQ-Demo-2026!` (set through `DEMO_PASSWORD` before seeding).

| Email | Role |
| --- | --- |
| `catherine.hale@alphabetabank.example` | Executive Viewer |
| `priya.raman@alphabetabank.example` | Risk Analyst |
| `daniel.okafor@alphabetabank.example` | Control Owner |
| `alex.morgan@alphabetabank.example` | Administrator |

See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for the scripted walkthrough of the four demo scenarios.

### Resetting the demo

- **UI:** sign in as Administrator → **Settings → Demo scenarios → Reset environment**, then type `RESET`.
- **CLI:** `python scripts/seed_demo.py` (add `--with-mfa-failure` to start with Scenario 1 applied).

## Configuration

Backend settings come from environment variables, or from `backend/.env`. See
[backend/.env.example](backend/.env.example).

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | `development` / `test` / `production`. In production the API refuses to start with a placeholder or short `SECRET_KEY`, or with `COOKIE_SECURE=false` |
| `DATABASE_URL` / `TEST_DATABASE_URL` | Application and test databases. They must differ, because the test database is wiped |
| `SECRET_KEY` | HMAC key for session-token hashing |
| `SESSION_TTL_HOURS`, `COOKIE_SECURE`, `COOKIE_SAMESITE` | Session cookie behaviour |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API |
| `EVIDENCE_STORAGE_DIR`, `EVIDENCE_MAX_BYTES` | Evidence file store and upload limit (default 2 MB) |
| `DEMO_PASSWORD` | Password assigned to the demo accounts by the seeder |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Optional LLM. Leave the key empty for rule-based intelligence |

Frontend: `CONTROLIQ_API_URL` (default `http://localhost:8000`).

## Tests

```powershell
# Backend: requires PostgreSQL and TEST_DATABASE_URL; the suite migrates and wipes that database
cd backend
python -m pytest -q

# Frontend
cd frontend
npm test              # Vitest unit tests (scoring mirror, formatting, API client)
npx tsc --noEmit      # type check
npm run lint
npm run build
```

The backend suite covers:

- the control engine and the evidence policy
- risk scoring
- the dependency graph
- evidence ingestion and integrity
- the findings workflow and risk acceptance
- assessment immutability and replay
- authorisation and audit
- intelligence and reports
- configuration guards
- an end-to-end lifecycle integration test (fail → finding → remediate → revalidate → resolve)

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Risk scoring methodology](docs/RISK_SCORING.md)
- [Security: demo controls vs. production hardening](docs/SECURITY.md)
- [Demo guide](docs/DEMO_GUIDE.md)

## Known limitations (demo scope)

- **No background scheduler.** Assessments run on demand. The 90-day history is produced by replaying
  scheduled runs through the engine at seed time.
- **Single instance.** The rate limiter and the run lock live in process. The PostgreSQL advisory lock
  serialises runs across processes, but rate limits do not hold across replicas.
- **Local authentication only.** There is no SSO, MFA, lockout or password reset for platform users.
- **No Content-Security-Policy** on application pages.
- **Manual evidence collection.** Evidence arrives by upload or the seeded and simulated connector;
  there are no live integrations.
- **Risk scores are prioritisation aids** and have not been statistically validated.
- **The LLM path has not been tested against a live provider.** The tests cover the rule-based path,
  the fallback-on-error path and the grounding check, the last two with a mocked model call.
- **The Docker Compose file has not been run in the development environment**, which used a native
  PostgreSQL 16 instead.
