// Mirrors backend permission keys. Used only to tailor the UI; the API enforces every check.
export const PERM = {
  READ: "platform:read",
  INTEL: "intelligence:use",
  REPORTS: "reports:generate",
  ASSETS_WRITE: "assets:write",
  ASSESSMENTS_RUN: "assessments:run",
  EVIDENCE_UPLOAD: "evidence:upload",
  FINDINGS_UPDATE: "findings:update",
  FINDINGS_UPDATE_ANY: "findings:update_any",
  ACCEPT_RISK: "findings:accept_risk",
  RISK_APPROVER: "risk:approve",
  RISKS_WRITE: "risks:write",
  SETTINGS_WRITE: "settings:write",
  AUDIT_READ: "audit:read",
  USERS_READ: "users:read",
  DEMO_MANAGE: "demo:manage",
  DEMO_RESET: "demo:reset",
} as const;
