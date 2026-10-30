"""Role-based access control. Permissions are enforced on every backend endpoint."""

READ = "platform:read"
INTEL_USE = "intelligence:use"
REPORTS_GENERATE = "reports:generate"
ASSETS_WRITE = "assets:write"
ASSESSMENTS_RUN = "assessments:run"
EVIDENCE_UPLOAD = "evidence:upload"
FINDINGS_UPDATE = "findings:update"
FINDINGS_UPDATE_ANY = "findings:update_any"
FINDINGS_ACCEPT_RISK = "findings:accept_risk"
RISK_APPROVER = "risk:approve"
RISKS_WRITE = "risks:write"
SETTINGS_WRITE = "settings:write"
AUDIT_READ = "audit:read"
USERS_READ = "users:read"
DEMO_MANAGE = "demo:manage"
DEMO_RESET = "demo:reset"

ALL_PERMISSIONS = [
    READ,
    INTEL_USE,
    REPORTS_GENERATE,
    ASSETS_WRITE,
    ASSESSMENTS_RUN,
    EVIDENCE_UPLOAD,
    FINDINGS_UPDATE,
    FINDINGS_UPDATE_ANY,
    FINDINGS_ACCEPT_RISK,
    RISK_APPROVER,
    RISKS_WRITE,
    SETTINGS_WRITE,
    AUDIT_READ,
    USERS_READ,
    DEMO_MANAGE,
    DEMO_RESET,
]

ROLE_DEFINITIONS = {
    "executive_viewer": {
        "name": "Executive Viewer",
        "description": "Read-only access to dashboards, reports and intelligence. May be named as an accountable "
        "approver for risk acceptance.",
        "permissions": [READ, INTEL_USE, REPORTS_GENERATE, RISK_APPROVER],
    },
    "risk_analyst": {
        "name": "Risk Analyst",
        "description": "Runs assessments, manages findings, risk register entries and evidence across all controls.",
        "permissions": [
            READ,
            INTEL_USE,
            REPORTS_GENERATE,
            ASSETS_WRITE,
            ASSESSMENTS_RUN,
            EVIDENCE_UPLOAD,
            FINDINGS_UPDATE,
            FINDINGS_UPDATE_ANY,
            FINDINGS_ACCEPT_RISK,
            RISKS_WRITE,
            USERS_READ,
            DEMO_MANAGE,
        ],
    },
    "control_owner": {
        "name": "Control Owner",
        "description": "Submits evidence and remediates findings for the controls they own or are assigned.",
        "permissions": [READ, INTEL_USE, REPORTS_GENERATE, ASSESSMENTS_RUN, EVIDENCE_UPLOAD, FINDINGS_UPDATE, USERS_READ],
    },
    "administrator": {
        "name": "Administrator",
        "description": "Full platform administration including configuration, audit log and demo environment reset.",
        "permissions": list(ALL_PERMISSIONS),
    },
}
