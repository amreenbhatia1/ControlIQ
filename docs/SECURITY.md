# ControlIQ — Security

> **Scope statement.** ControlIQ is a demonstration MVP running on **synthetic data** for a fictional
> organisation (Alpha Beta Bank). It implements common application-security controls, but
> **implementing those controls does not make the system compliant with any banking regulation,
> security standard or supervisory expectation**. No compliance assessment has been performed. A real
> deployment would need the production-hardening work listed at the end of this document, plus an
> independent security review and penetration test.

This document separates **what is implemented and tested in the demo** from **what production would
additionally require**.

## 1. Implemented in the demo

### Authentication and sessions

| Control | Implementation |
| --- | --- |
| Password storage | Argon2id (`argon2-cffi` defaults). A dummy hash is verified for unknown users so response timing does not reveal which emails exist |
| Generic failure message | Every login failure returns `401 Invalid email or password` |
| Session tokens | 256-bit random token (`secrets.token_urlsafe(32)`) in an `HttpOnly` cookie (`controliq_session`), `SameSite=Lax`, `Secure` when `COOKIE_SECURE=true`, 12-hour TTL |
| Token storage | Only `HMAC-SHA256(SECRET_KEY, token)` is stored in `user_sessions`, so a database read does not reveal usable session tokens |
| Logout | Deletes the server-side session and clears the cookie |
| Inactive or non-login users | Rejected at login and on every authenticated request |
| Production startup check | With `ENVIRONMENT=production` the API refuses to start if `SECRET_KEY` is a placeholder or shorter than 32 characters, or if `COOKIE_SECURE` is false |

### Authorisation (enforced in the backend)

Every endpoint declares its required permission through the `require(...)` FastAPI dependency. Hiding
controls in the UI is a convenience only. The API returns `403` regardless of what the client renders.
Every denial, whether it comes from a missing role permission or an object-level rule, is written to
the audit log as `authz.denied` with the endpoint and reason. Any uncommitted work from the denied
request is rolled back first.

| Permission | Executive Viewer | Risk Analyst | Control Owner | Administrator |
| --- | :-: | :-: | :-: | :-: |
| `platform:read`, `intelligence:use`, `reports:generate` | ✓ | ✓ | ✓ | ✓ |
| `risk:approve` (can be named as accountable approver) | ✓ | | | ✓ |
| `assessments:run`, `evidence:upload`, `findings:update` | | ✓ | ✓ | ✓ |
| `findings:update_any` (any finding, validation sign-off) | | ✓ | | ✓ |
| `findings:accept_risk`, `risks:write`, `assets:write`, `demo:manage` | | ✓ | | ✓ |
| `users:read` | | ✓ | ✓ | ✓ |
| `settings:write`, `audit:read`, `demo:reset` | | | | ✓ |

Object-level rules on top of permissions:

- **Control Owners** may update only findings for controls they own or findings assigned to them.
- **Risk acceptance** requires an approver who holds `risk:approve`, is active, and is *not* the person
  recording the acceptance (segregation of duties). The justification must be at least 40 characters
  and the expiry is capped by severity.
- **Resolution** cannot be requested manually. Only a passing reassessment against updated evidence
  can resolve a finding.

### Request-level protections

| Control | Implementation |
| --- | --- |
| CSRF | `SameSite=Lax` cookie plus an Origin check: `POST/PUT/PATCH/DELETE` with an `Origin` that is neither the API host nor in `CORS_ORIGINS` returns `403 Origin not allowed` |
| CORS | Explicit allow-list from `CORS_ORIGINS` (default `http://localhost:3000`), credentials allowed, restricted methods and headers |
| Security headers | API: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`. Frontend: `X-Frame-Options`, `nosniff`, `Referrer-Policy` |
| Error handling | Unhandled exceptions return a generic `500` with a correlation `error_id`; stack traces go only to server logs |
| Input validation | Pydantic schemas with length, pattern and range constraints. Controlled vocabularies are also enforced by database `CHECK` constraints |
| SQL injection | All queries use SQLAlchemy expressions or bound parameters; no string-built SQL from user input |

### Rate limiting

In-process sliding-window limiter, keyed by endpoint and client IP. Exceeding a limit returns
`429` with `Retry-After`.

| Endpoint | Limit |
| --- | --- |
| `POST /auth/login` | 10 per 60 s |
| `POST /assessments/run` | 6 per 60 s |
| `POST /evidence/upload` | 20 per 60 s |
| `GET /reports/{type}/pdf` | 20 per 60 s |
| `POST /intelligence/ask`, `/executive-summary` | 30 per 60 s |
| `POST /demo/reset` | 3 per 300 s |

### Evidence handling

Uploaded evidence is treated as untrusted:

- **Extension allow-list:** `.json`, `.csv`, `.pdf`, `.txt`, `.log`. Maximum 2 MB (`EVIDENCE_MAX_BYTES`).
  CSV files are limited to 5,000 rows.
- **Content checks:** PDFs must start with the `%PDF-` signature. Text formats must be valid UTF-8 with
  no NUL bytes. Structured evidence is validated against the schema for its category. Invalid
  evidence is stored as `Invalid` and **cannot make a control Effective**.
- **Storage:** files are content-addressed as `<sha256>.<ext>` under `EVIDENCE_STORAGE_DIR` with exclusive
  creation. The client-supplied filename is never used as a path. Downloads are served with
  `Content-Disposition: attachment` and a sandboxing `Content-Security-Policy: default-src 'none'; sandbox`.
- **Integrity:** the SHA-256 is recorded at upload and re-verified by `POST /evidence/{id}/verify`, on
  every download (a mismatched file is refused with `409` instead of being served) and during
  assessment replay.
- **No execution:** evidence is parsed as data only. No macros, scripts or embedded instructions are run.

### Integrity of the control record

- `control_assessments` rows cannot be updated, enforced by a PostgreSQL trigger and an ORM guard.
  Deletion is possible only inside an explicit `SET LOCAL controliq.allow_purge = 'on'` transaction,
  which only the confirmed demo reset uses.
- Each assessment stores a SHA-256 input hash, and `POST /assessments/{id}/replay` re-verifies it.
- The activity history (`remediation_activity`) and the audit log (`audit_logs`) are append-only in the
  application. No API updates or deletes them; see the production items below.

### Audit logging

Recorded events include successful and failed logins, logouts, permission denials, assessment runs,
evidence uploads, finding status changes, assignments, risk acceptances, validation sign-offs, risk
register edits, settings changes, report generation, AI questions, demo scenarios and demo resets.
Each entry stores the actor, action, entity, outcome, IP address and structured details. Administrators
view the log in **Settings → Audit log**.

### AI safety

- The assistant is optional. Without `OPENAI_API_KEY`, answers are built deterministically from
  templates over stored records and labelled **"Rule-based intelligence"**.
- With a key configured, the model receives only the records retrieved for the question. Evidence
  content is passed in fields prefixed `untrusted_`, and the system prompt instructs the model never
  to follow instructions inside them.
- Responses are checked for IDs that do not appear in the retrieved records, and any found are flagged
  to the user.
- If the model call fails, the user sees the rule-based answer **with an explicit notice** that the AI
  service was unavailable. The substitution is never silent.
- The assistant has no write capabilities. It cannot create or alter evidence, change findings or
  approve risk acceptance.

### Secrets and data

- All secrets come from environment variables (`backend/.env`, which git ignores). Only
  `.env.example` files with placeholder values are committed.
- All organisations, people, systems and figures are fictional and use the reserved `.example` domain.
  No real customer or bank data is present.

### Demo reset

`POST /demo/reset` requires the `demo:reset` permission (Administrator only) **and** a request body of
`{"confirm": "RESET"}`. The UI requires typing `RESET` in a confirmation dialog. Resets are rate-limited
and audit-logged.

## 2. Production hardening (not implemented in the demo)

| Area | Requirement |
| --- | --- |
| Identity | Enterprise SSO (SAML/OIDC) with MFA for all users. Joiner/mover/leaver integration. The demo uses local passwords with no MFA, account lockout or password-reset flow |
| Transport | TLS everywhere, HSTS, `COOKIE_SECURE=true` (enforced at startup when `ENVIRONMENT=production`). Consider the `__Host-` cookie prefix |
| Content Security Policy | No CSP header is set. Add a strict CSP (nonces for Next.js scripts) |
| Rate limiting | Replace the in-process limiter with a shared store (Redis) or API gateway so limits hold across replicas. Put a trusted proxy in front and configure which forwarded-for headers to trust |
| Session management | Idle timeout, concurrent-session limits, session listing and revocation for administrators |
| Secrets | Use a secrets manager or KMS instead of `.env` files. Rotate `SECRET_KEY` and database credentials |
| Database | Least-privilege database roles: the application role should not own tables or be able to disable triggers. Encryption at rest, backups, point-in-time recovery |
| Tamper evidence | Write audit logs and assessment records to WORM storage or a hash-chained ledger, and forward audit events to a SIEM. Today, immutability relies on database triggers that a DBA can bypass |
| Evidence | Object storage with server-side encryption and retention locks. Malware scanning of uploads. Signed evidence collection from source systems instead of manual upload |
| Scheduling | A durable job scheduler for the control frequencies (Daily, Weekly and so on). The demo runs assessments on demand, and the 90-day history is replayed by the seed script |
| Availability | Multiple API instances, health-based routing, a managed PostgreSQL with high availability |
| AI | A data-processing agreement and data-residency review before sending any record to an external model. Prompt and response logging with retention controls. Red-team testing of prompt-injection defences |
| Assurance | Threat modelling, SAST/DAST, dependency scanning, penetration testing, and formal control-mapping review by compliance, before any regulatory claim is made |
