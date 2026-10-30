# ControlIQ — Demo Guide

A 15–20 minute walkthrough for a Chief Technology Controls Officer audience. Every number on screen
comes from rule evaluations over synthetic evidence for the fictional **Alpha Beta Bank**.

## Before you start

1. Start PostgreSQL, the API and the frontend (see the [README](../README.md#running-locally)).
2. Reset to a clean baseline:
   - **From the command line:** `python scripts/seed_demo.py` (repository root, with the backend virtualenv)
   - **In the UI:** sign in as Administrator → **Settings → Demo scenarios → Reset environment**, then
     type `RESET` to confirm
3. Open <http://localhost:3000>.

### Demo accounts

All accounts use the password `ControlIQ-Demo-2026!` (configurable through `DEMO_PASSWORD`).

| Persona | Email | Role | Use for |
| --- | --- | --- | --- |
| Catherine Hale | `catherine.hale@alphabetabank.example` | Executive Viewer | Read-only executive view; can be named as risk-acceptance approver |
| Priya Raman | `priya.raman@alphabetabank.example` | Risk Analyst | **Main presenter account**: runs assessments, manages findings, runs scenarios |
| Daniel Okafor | `daniel.okafor@alphabetabank.example` | Control Owner | Owns the identity controls; uploads evidence and remediates own findings |
| Alex Morgan | `alex.morgan@alphabetabank.example` | Administrator | Settings, audit log, environment reset |

## Suggested flow

### 1. Executive Overview (2 min) — Priya

- KPIs: control effectiveness, Critical findings, overdue remediation, risk-accepted findings.
- **Business services at potential exposure**: ranked by an exposure index computed from unresolved
  findings in each service's dependency chain. It is labelled *potential* exposure, not an incident.
- **90-day trend**: built by replaying scheduled assessments through the real engine at seed time.
- **Executive summary** card: shows the **"Rule-based intelligence"** label when no AI key is configured.

### 2. Scenario 1 — Privileged MFA failure (4 min)

**Settings → Demo scenarios**, panel *Scenario 1 & 4*. Each button calls the real backend services.

1. **Inject failure evidence.** The simulated identity connector delivers a privileged-account export for
   `IDP-CORE-001` in which two admin accounts have MFA disabled. The evidence is ingested, schema-validated
   and SHA-256 hashed like any other upload. *Live scenario state* shows the new evidence as
   "Newer than the latest assessment — awaiting a run".
2. **Run Control Assessment.** The engine evaluates every active control. `CTRL-IAM-001` on `IDP-CORE-001`
   records an immutable **Ineffective** assessment and raises a new **Critical** finding.
3. **Open the finding** and walk through:
   - **Plain-English explanation** naming the failing accounts.
   - **Risk score breakdown**: five factors with inputs, weights and contributions. Note that the
     compensating control (Security Logging) earns credit only when it is itself Effective. Use the
     **what-if** panel to show how weights change the score without saving anything.
   - **Business impact**: services that depend on the identity provider directly or transitively.
     Click **Trace business impact** to open the dependency map centred on the asset.
   - **Traceability**: linked register risk → control → assessment → evidence (with hash).

### 3. Workflow guard-rails (2 min)

On the same finding:

- The status menu has **no "Resolved" option**. The API also rejects it: *"Findings cannot be resolved
  manually…"*.
- **Accept risk** requires a justification of at least 40 characters, an accountable approver who is
  not you (for example Catherine Hale), and an expiry no more than 90 days away for a Critical finding.
  Try naming yourself as approver to show the segregation-of-duties error. Don't complete the
  acceptance if you plan to continue with Scenario 4.
- **Optional:** sign in as Catherine (Executive Viewer). The run, upload and status-change actions
  are hidden, and calling the API directly returns `403`. Each denial appears in the audit log.

### 4. Scenario 4 — Remediated evidence and validation (3 min)

Back in **Settings → Demo scenarios** as Priya:

1. **Upload remediated export.** A post-remediation export with all privileged accounts MFA-enrolled
   goes through the standard evidence service.
   - *Manual alternative:* click **Download export for manual upload**, then in **Evidence Center → Upload
     evidence** choose category *Privileged accounts*, asset `IDP-CORE-001`, and upload the file.
2. **Run Control Assessment** again. A new **Effective** assessment is recorded and the finding is
   **Resolved, validated by the passing assessment** (validation mode `auto_resolve`). Under
   `analyst_signoff` mode (Settings → Validation workflow) the finding moves to **Pending
   Validation** and an analyst confirms it.
3. Show that history is preserved: the finding timeline keeps both assessments, the activity log
   records the resolution, and *Assessment history retained* counts every immutable assessment for the
   scope. On any assessment page, **Replay & verify** re-executes the rule and confirms the result,
   explanation, input hash and evidence hash.

### 5. Scenario 2 — Critical vulnerability SLA breach (2 min)

Seeded state: `CTRL-VM-001` (Critical Vulnerability Remediation) on `WEB-BANK-001`, the internet-facing
online banking web tier. Open it from the *Scenario 2* card or **Findings** (**FND-0017** in a fresh seed).

- A known-exploited critical vulnerability is past the 15-day SLA.
- The score is near the maximum (99/100) because every factor is at or near its ceiling:
  Critical control, Critical asset, internet-exposed with exploit uplift, Tier 1 services, and no
  effective compensating credit.
- An open remediation action and its owner show the remediation plan.

### 6. Scenario 3 — Overdue backup recovery test (2 min)

Seeded state: `CTRL-BCP-001` (Backup Recovery Testing) on `DB-TXN-001`, the payment transaction
database. Open it from the *Scenario 3* card or **Findings** (**FND-0006** in a fresh seed).

- No successful restore test within 180 days. This control is configured to treat an overdue test as
  **Ineffective** rather than Needs Review.
- The score is High rather than Critical. The asset is Critical and supports Tier 1 services, but it is
  internal-only, so the exposure factor is low. This shows the score is explainable rather than a black box.
- Use **Business Services** to show Payment Processing's dependency chain down to the database.

### 7. Risk intelligence and reporting (2 min)

- **Risk Intelligence**: ask one of the suggested questions, for example *"Which findings affect payment
  processing?"* or *"Why is FND-… considered critical?"* (pre-filled with the current top finding).
  Each answer separates **Facts** (with record citations) from **Recommendations**. Without an API key
  it is labelled **Rule-based intelligence**.
- **Reports**: preview the *Executive Technology Risk Summary* and **Export PDF**. The other report types
  are Control Effectiveness, Critical Findings, Remediation Aging and Business Services Risk. Each PDF
  carries the synthetic-data disclaimer, and each export is recorded in report history with its SHA-256.

### 8. Close (1 min) — Alex

- **Settings → Audit log**: logins, permission denials, assessment runs, uploads, workflow changes,
  AI questions.
- **Settings → Risk scoring**: weights are configurable and validated to sum to 1.0, with no code
  change needed.

## Resetting between demos

**Settings → Demo scenarios → Reset environment** (Administrator only) asks you to type `RESET`.
It deletes and regenerates the synthetic dataset, including the 90-day assessment history, and
restores the baseline findings. The reset is audit-logged and rate-limited (3 per 5 minutes).

Equivalent command-line reset:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\backend\.venv\Scripts\python.exe scripts\seed_demo.py
```

Add `--with-mfa-failure` to seed with Scenario 1 already applied (failing evidence injected and an
assessment run, so the MFA finding is open).

## Talking points and honest caveats

- Assessments here run **on demand**. The 90-day history was produced by replaying scheduled runs at
  seed time. A production deployment needs a job scheduler.
- Risk scores are a **prioritisation aid**, not a statistically validated loss or likelihood estimate.
- The platform implements common security controls but is **not** presented as compliant with any
  specific banking regulation.
- All data is synthetic.
