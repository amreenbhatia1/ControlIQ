"""Controlled vocabularies. Stored as strings and enforced with CHECK constraints."""

ASSET_TYPES = (
    "Server",
    "Database",
    "Cloud Resource",
    "Application",
    "Network Device",
    "Identity Service",
    "Third-Party Integration",
)
ENVIRONMENTS = ("Production", "Disaster Recovery", "Staging", "Development")
CRITICALITY = ("Critical", "High", "Medium", "Low")
LIFECYCLE = ("Active", "Planned", "Decommissioning", "Retired")
SERVICE_TIERS = ("Tier 1", "Tier 2", "Tier 3")

CONTROL_DOMAINS = (
    "Identity and Access Management",
    "Vulnerability Management",
    "Endpoint Security",
    "Data Protection",
    "Logging and Monitoring",
    "Backup and Recovery",
    "Change Management",
    "Third-Party Risk",
)
FREQUENCIES = ("Daily", "Weekly", "Monthly", "Quarterly")
FREQUENCY_DAYS = {"Daily": 1, "Weekly": 7, "Monthly": 30, "Quarterly": 90}

ASSESSMENT_RESULTS = ("Effective", "Ineffective", "Needs Review", "Not Assessed")
EFFECTIVE, INEFFECTIVE, NEEDS_REVIEW, NOT_ASSESSED = ASSESSMENT_RESULTS

SEVERITIES = ("Critical", "High", "Medium", "Low")

FINDING_STATUSES = ("Open", "In Progress", "Pending Validation", "Resolved", "Risk Accepted")
ACTIVE_FINDING_STATUSES = ("Open", "In Progress", "Pending Validation", "Risk Accepted")
UNRESOLVED_FINDING_STATUSES = ("Open", "In Progress", "Pending Validation")

REMEDIATION_STATUSES = ("Planned", "In Progress", "Completed", "Cancelled")

EVIDENCE_FORMATS = ("json", "csv", "pdf", "text")
EVIDENCE_VALIDATION = ("Valid", "Invalid", "Unstructured")

RISK_CATEGORIES = (
    "Cyber Security",
    "Technology Resilience",
    "Data Management",
    "Third-Party",
    "Change & Release",
    "Identity & Access",
)
RISK_RATINGS = ("Critical", "High", "Medium", "Low")
TREATMENTS = ("Mitigate", "Accept", "Transfer", "Avoid")
RISK_STATUSES = ("Open", "Monitoring", "Closed")


def check_in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"{column} IN ({quoted})"
