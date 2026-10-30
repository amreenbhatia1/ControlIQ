# ControlIQ — Risk Scoring Methodology

> **Disclaimer.** The ControlIQ risk score is a deterministic *prioritisation aid* computed from
> configured weights. It is **not** a statistically validated prediction of financial loss or incident
> likelihood, and it has not been calibrated against loss data. Use it to sequence remediation, not to
> quantify risk capital.

Implementation: `backend/app/risk/scoring.py` (methodology version `1.0`). The score is calculated
when an assessment returns **Ineffective**, and stored with its full factor breakdown on the finding
(`findings.score_breakdown`). The UI shows every factor, its inputs, its weight and its contribution.

## Formula

```
score = round( Σ  value_f × weight_f × 100 )        value_f ∈ [0, 1],  Σ weight_f = 1
```

Each contribution is rounded to two decimal places before the sum. The total is rounded to an integer
with Python's `round` (round-half-to-even) and clamped to 0–100. The frontend what-if simulator uses
the same rounding, so an unmodified simulation reproduces the recorded score exactly.

## Factors and default weights

| Factor | Default weight | Value (0–1) |
| --- | --- | --- |
| Control failure severity | 0.25 | `base × (0.8 + 0.2 × failure magnitude)`. Base comes from the control's failure severity: Critical 1.0, High 0.75, Medium 0.5, Low 0.25. *Failure magnitude* (0–1) is reported by the rule, for example the share of privileged accounts without MFA or how far a backup test is overdue |
| Asset criticality | 0.20 | Asset criticality on the same scale: Critical 1.0, High 0.75, Medium 0.5, Low 0.25 |
| Exposure & exploit intelligence | 0.20 | Internet-exposed 1.0; privileged-access hub 0.8; internal 0.4. For vulnerability-scan controls, +0.2 when a failing item is flagged as known-exploited (capped at 1.0) |
| Business service criticality | 0.20 | Highest dependent service tier: Tier 1 1.0, Tier 2 0.65, Tier 3 0.35, plus 0.05 per additional dependent service (capped at 1.0). Includes services that depend directly *or transitively* on the asset. 0.2 if no service depends on it |
| Compensating control weakness | 0.15 | `1 − credit`, where credit is the sum of configured credits for compensating controls that are **currently Effective on the same asset**. Compensating controls that are failing or unassessed earn no credit |

Compensating controls are configured per control in `rule_parameters`. In the seed data,
CTRL-IAM-001 (Privileged MFA) gets 0.15 credit from CTRL-LOG-001 (Security Logging) and CTRL-VM-001
(Critical Vulnerability Remediation) gets 0.10 credit from CTRL-END-001 (Endpoint Protection).

## Severity bands

| Score | Severity |
| --- | --- |
| ≥ 80 | Critical |
| 60–79 | High |
| 40–59 | Medium |
| < 40 | Low |

The finding's severity drives its remediation SLA (Critical 14 days, High 30, Medium 60, Low 90) and
the maximum risk-acceptance duration.

## Configuration

Administrators can change the weights under **Settings → Risk scoring** (`PUT /api/v1/settings/risk-scoring`).
Weights must cover exactly these five factors, each between 0 and 1, and sum to 1.0 (±0.001).
Invalid configurations are rejected. A change applies to scores calculated by later assessments;
**existing findings keep the score and breakdown recorded when they were assessed**, so history stays
reproducible. The finding page offers a client-side *what-if* simulator that recalculates a score
with modified factor values or weights without persisting anything.

## Worked examples (seeded data)

These breakdowns were read from the seeded database. Exact magnitudes depend on the seed date.

**FND-0017 — CTRL-VM-001 on WEB-BANK-001 (internet banking web tier)**

| Factor | Value | Weight | Contribution |
| --- | --- | --- | --- |
| Control failure severity | 0.9733 (Critical, high magnitude) | 0.25 | 24.33 |
| Asset criticality | 1.0 (Critical) | 0.20 | 20.00 |
| Exposure | 1.0 (internet-exposed, known-exploited) | 0.20 | 20.00 |
| Business service | 1.0 (Tier 1, several services) | 0.20 | 20.00 |
| Compensating weakness | 1.0 (no effective compensating credit) | 0.15 | 15.00 |
| **Score** | | | **99 → Critical** |

**FND-0006 — CTRL-BCP-001 on DB-TXN-001 (core transaction database)**

| Factor | Value | Weight | Contribution |
| --- | --- | --- | --- |
| Control failure severity | 0.6509 (High base 0.75, magnitude ≈ 0.34) | 0.25 | 16.27 |
| Asset criticality | 1.0 (Critical) | 0.20 | 20.00 |
| Exposure | 0.4 (internal only) | 0.20 | 8.00 |
| Business service | 1.0 (Tier 1, several services) | 0.20 | 20.00 |
| Compensating weakness | 1.0 (none defined) | 0.15 | 15.00 |
| **Score** | | | **79 → High** |

The second example shows why exposure matters: the same Critical asset and Tier 1 dependency produce
a High rather than Critical score because the database is not internet-reachable.

## Service-level potential exposure

For each business service, ControlIQ collects every unresolved finding (Open, In Progress or Pending
Validation; risk-accepted findings are excluded) on assets in the service's dependency closure and
computes:

```
potential exposure index = 0.7 × max(score) + 0.3 × mean(top 3 scores)
```

This index ranks services on the Executive Overview and the Business Services map. It is always
labelled *potential exposure*: a failing control on a dependency is a weakness, not evidence that the
service has been affected.

## Known limitations

- Weights and factor values are expert-judgement defaults, not empirically derived.
- Factors are combined additively, so there are no interaction effects. For example, internet exposure
  does not amplify the severity factor.
- The exploit uplift relies on the `known_exploited` flag in the vulnerability evidence. No external
  threat-intelligence feed is integrated.
- Factor values are capped at 1.0, so very broad service dependency saturates quickly.
