from sqlalchemy.orm import Session

from app.models import AppSetting
from app.risk.scoring import DEFAULT_BANDS, DEFAULT_WEIGHTS

VALIDATION_MODES = ("auto_resolve", "analyst_signoff")

DEFAULTS: dict[str, dict] = {
    "risk_scoring": {
        "value": {"weights": DEFAULT_WEIGHTS, "bands": DEFAULT_BANDS},
        "description": "Risk scoring factor weights and severity bands.",
    },
    "validation_workflow": {
        "value": {"mode": "auto_resolve"},
        "description": "auto_resolve: a passing reassessment resolves the finding. analyst_signoff: a passing "
        "reassessment moves the finding to Pending Validation until a Risk Analyst confirms.",
    },
    "remediation_sla_days": {
        "value": {"Critical": 14, "High": 30, "Medium": 60, "Low": 90},
        "description": "Remediation due date offsets by finding severity.",
    },
}


def get_setting(db: Session, key: str) -> dict:
    row = db.get(AppSetting, key)
    if row is None:
        return dict(DEFAULTS[key]["value"])
    return row.value


def set_setting(db: Session, key: str, value: dict, user_id: int | None) -> AppSetting:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value, description=DEFAULTS[key]["description"], updated_by_id=user_id)
        db.add(row)
    else:
        row.value = value
        row.updated_by_id = user_id
    return row


def ensure_defaults(db: Session) -> None:
    for key, spec in DEFAULTS.items():
        if db.get(AppSetting, key) is None:
            db.add(AppSetting(key=key, value=spec["value"], description=spec["description"]))
