"""Evidence ingestion: validation, integrity hashing and content-addressed storage.

Uploaded content is treated as untrusted data: it is never executed, never rendered as HTML,
and never interpreted as instructions by the intelligence layer.
"""

import csv
import hashlib
import io
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.controls.evidence_schemas import CSV_LIST_FIELDS, EVIDENCE_SCHEMAS, validate_payload
from app.core.config import get_settings
from app.core.time import parse_iso, utcnow
from app.models import Asset, Control, Evidence, User

EXTENSIONS = {"json": ".json", "csv": ".csv", "pdf": ".pdf", "text": ".txt"}
ALLOWED_EXTENSIONS = {".json": "json", ".csv": "csv", ".pdf": "pdf", ".txt": "text", ".log": "text"}
STRUCTURED_FORMATS = ("json", "csv")


class EvidenceError(ValueError):
    pass


def storage_root() -> Path:
    root = Path(get_settings().evidence_storage_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _detect_format(filename: str, content: bytes) -> str:
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise EvidenceError("Unsupported file type. Allowed: .json, .csv, .pdf, .txt, .log")
    fmt = ALLOWED_EXTENSIONS[ext]
    if fmt == "pdf":
        if not content.startswith(b"%PDF-"):
            raise EvidenceError("File content does not match the PDF format")
    else:
        if b"\x00" in content:
            raise EvidenceError("Binary content is not permitted for text-based evidence")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise EvidenceError("Text-based evidence must be UTF-8 encoded") from exc
    return fmt


def _coerce_csv_value(value: str):
    v = value.strip()
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("", "null", "none"):
        return None
    if v.isdigit():
        return int(v)
    return v


def _parse_csv(text: str, category: str, asset_id: str | None) -> dict:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise EvidenceError("CSV evidence must include a header row")
    rows = [{k.strip(): _coerce_csv_value(v or "") for k, v in row.items() if k} for row in reader]
    if len(rows) > 5000:
        raise EvidenceError("CSV evidence is limited to 5,000 rows")
    list_field = CSV_LIST_FIELDS.get(category)
    if list_field:
        return {"asset_id": asset_id, list_field: rows}
    if len(rows) != 1:
        raise EvidenceError(f"CSV evidence for '{category}' must contain exactly one data row")
    payload = dict(rows[0])
    payload.setdefault("asset_id", asset_id)
    return payload


def _store(content: bytes, sha256: str, fmt: str) -> str:
    name = f"{sha256}{EXTENSIONS[fmt]}"
    path = storage_root() / name
    if not path.exists():
        # Exclusive create; content-addressed names mean an existing file is identical.
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o640)
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
        except FileExistsError:
            pass
    return name


def ingest_evidence(
    db: Session,
    *,
    content: bytes,
    filename: str,
    category: str,
    source: str,
    asset_id: str | None,
    control_id: str | None = None,
    collected_at: datetime | None = None,
    description: str = "",
    uploaded_by: User | None = None,
    uploaded_at: datetime | None = None,
    now: datetime | None = None,
) -> Evidence:
    settings = get_settings()
    now = now or utcnow()
    if len(content) == 0:
        raise EvidenceError("Evidence file is empty")
    if len(content) > settings.evidence_max_bytes:
        raise EvidenceError(f"Evidence exceeds the {settings.evidence_max_bytes // 1024} KB size limit")
    safe_name = os.path.basename(filename or "evidence").strip()[:200] or "evidence"
    fmt = _detect_format(safe_name, content)

    if category != "supporting_document" and category not in EVIDENCE_SCHEMAS:
        raise EvidenceError(f"Unknown evidence category '{category}'")
    if category != "supporting_document" and fmt not in STRUCTURED_FORMATS:
        raise EvidenceError("Structured evidence categories require JSON or CSV content")

    if asset_id is not None and db.get(Asset, asset_id) is None:
        raise EvidenceError(f"Asset '{asset_id}' does not exist")
    if control_id is not None:
        control = db.get(Control, control_id)
        if control is None:
            raise EvidenceError(f"Control '{control_id}' does not exist")
        if category != "supporting_document" and control.evidence_category != category:
            raise EvidenceError(
                f"Control {control_id} consumes '{control.evidence_category}' evidence, not '{category}'"
            )

    payload = None
    errors: list[str] = []
    if fmt in STRUCTURED_FORMATS:
        text = content.decode("utf-8-sig")
        try:
            payload = json.loads(text) if fmt == "json" else _parse_csv(text, category, asset_id)
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"Invalid JSON: {exc.msg} at line {exc.lineno}") from exc
        if isinstance(payload, dict) and asset_id and payload.get("asset_id") not in (None, asset_id):
            errors.append(f"Payload asset_id '{payload.get('asset_id')}' does not match selected asset '{asset_id}'")
        if isinstance(payload, dict) and asset_id is None:
            asset_id = payload.get("asset_id")
            if asset_id is not None and db.get(Asset, asset_id) is None:
                raise EvidenceError(f"Asset '{asset_id}' referenced in evidence does not exist")
        _, schema_errors = validate_payload(category, payload)
        errors.extend(schema_errors)
        status = "Valid" if not errors else "Invalid"
        if collected_at is None and isinstance(payload, dict) and payload.get("collected_at"):
            try:
                collected_at = parse_iso(payload["collected_at"])
            except ValueError:
                errors.append("collected_at: not a valid ISO-8601 timestamp")
                status = "Invalid"
    else:
        status = "Unstructured"

    collected_at = collected_at or now
    if collected_at > now + timedelta(minutes=5):
        raise EvidenceError("Collection timestamp cannot be in the future")

    sha256 = hashlib.sha256(content).hexdigest()
    file_ref = _store(content, sha256, fmt)
    evidence = Evidence(
        evidence_category=category,
        file_format=fmt,
        source=source[:160],
        description=description[:2000],
        collected_at=collected_at,
        uploaded_at=uploaded_at or now,
        uploaded_by_id=uploaded_by.id if uploaded_by else None,
        asset_id=asset_id,
        control_id=control_id,
        sha256=sha256,
        validation_status=status,
        validation_errors=errors,
        file_ref=file_ref,
        original_filename=safe_name,
        size_bytes=len(content),
        payload=payload if status != "Unstructured" else None,
    )
    db.add(evidence)
    db.flush()
    return evidence


def read_evidence_file(evidence: Evidence) -> bytes:
    path = (storage_root() / evidence.file_ref).resolve()
    if storage_root().resolve() not in path.parents:
        raise EvidenceError("Invalid evidence file reference")
    return path.read_bytes()


def verify_integrity(evidence: Evidence) -> dict:
    try:
        content = read_evidence_file(evidence)
    except FileNotFoundError:
        return {"verified": False, "reason": "Stored file not found", "expected_sha256": evidence.sha256}
    actual = hashlib.sha256(content).hexdigest()
    return {
        "verified": actual == evidence.sha256,
        "expected_sha256": evidence.sha256,
        "actual_sha256": actual,
        "reason": "Hash matches stored integrity value" if actual == evidence.sha256 else "Hash mismatch",
    }
