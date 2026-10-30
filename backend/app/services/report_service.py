"""Executive reports generated from live database records, rendered as JSON (preview) or PDF."""

import hashlib
import io
from datetime import timedelta

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utcnow
from app.models import (
    AssessmentRun,
    Control,
    ControlAssessment,
    ControlAssetScope,
    Evidence,
    Finding,
    RemediationAction,
    User,
)
from app.models.enums import UNRESOLVED_FINDING_STATUSES
from app.services import dashboard_service, intelligence_service
from app.services.graph_service import load_graph

REPORT_TYPES = {
    "executive_summary": "Executive Technology Risk Summary",
    "control_effectiveness": "Control Effectiveness Report",
    "critical_findings": "Critical Findings Report",
    "remediation_aging": "Remediation Aging Report",
    "business_services": "Business Services Risk Report",
}

DISCLAIMER = (
    "Synthetic demonstration environment — no production banking data. All organisations, systems, people and "
    "vulnerabilities are fictional. Risk scores are prioritisation aids, not predictions of loss."
)


def _d(dt):
    return dt.strftime("%d %b %Y") if dt else "—"


def _kpis(items):
    return {"kind": "kpis", "items": items}


def _section(key, title, body: dict, note: str | None = None):
    return {"key": key, "title": title, "note": note, **body}


# --------------------------------------------------------------------------- shared builders
def _coverage(db: Session, start) -> dict:
    scopes = db.scalar(select(func.count()).select_from(ControlAssetScope)) or 0
    assessed_scopes = db.scalar(
        select(func.count(func.distinct(ControlAssessment.scope_identifier))).where(ControlAssessment.assessed_at >= start)
    ) or 0
    runs = db.scalar(select(func.count()).select_from(AssessmentRun).where(AssessmentRun.evaluated_at >= start)) or 0
    assessments = db.scalar(select(func.count()).select_from(ControlAssessment).where(ControlAssessment.assessed_at >= start)) or 0
    evidence = db.scalar(select(func.count()).select_from(Evidence).where(Evidence.collected_at >= start)) or 0
    return {"scopes": scopes, "assessed_scopes": assessed_scopes, "runs": runs, "assessments": assessments, "evidence": evidence}


def _trend_section(db: Session, days: int):
    pts = dashboard_service.trend(db, days)
    return _section(
        "trend",
        "Control effectiveness trend",
        {"kind": "trend", "points": [{"label": _d(p["evaluated_at"]), "value": p["effectiveness_rate"]} for p in pts]},
        "Effective instances as a percentage of assessed instances per assessment run.",
    )


def _failing_evidence_refs(db: Session) -> list[list[str]]:
    rows = []
    for scope in db.scalars(
        select(ControlAssetScope).where(ControlAssetScope.current_status.in_(("Ineffective", "Needs Review"))).order_by(ControlAssetScope.control_id)
    ):
        a = db.get(ControlAssessment, scope.latest_assessment_id) if scope.latest_assessment_id else None
        if a is None:
            continue
        ev = a.evidence[0] if a.evidence else None
        rows.append([a.control_id, scope.asset_id, a.result, a.ref, ev.ref if ev else "None on record",
                     ev.sha256[:16] + "…" if ev else "—"])
    return rows


def _evidence_section(db: Session):
    return _section(
        "evidence",
        "Evidence references",
        {"kind": "table", "columns": ["Control", "Asset", "Result", "Assessment", "Evidence", "SHA-256"],
         "rows": _failing_evidence_refs(db)},
        "Evidence underpinning every non-effective control instance. Each assessment is reproducible from these inputs.",
    )


def _findings_rows(findings):
    now = utcnow()
    return [
        [f.ref, f.title, f.service.name if f.service else "—", str(f.risk_score), f.severity, f.status,
         f.assigned_owner.full_name if f.assigned_owner else "Unassigned", f"{(now - f.detected_at).days}d", _d(f.due_date)]
        for f in findings
    ]


FINDING_COLUMNS = ["ID", "Finding", "Service", "Score", "Severity", "Status", "Owner", "Age", "Due"]


def _recommendations(db: Session) -> list[str]:
    ans = intelligence_service.answer_question(db, "executive summary", prefer_ai=False)
    return ans.recommendations or ["No priority actions identified from current records."]


# --------------------------------------------------------------------------- report types
def _executive(db: Session, days: int, start):
    k = dashboard_service.kpis(db)
    cov = _coverage(db, start)
    summary = intelligence_service.answer_question(db, "executive summary", prefer_ai=False)
    top = dashboard_service.critical_attention(db, 5)
    svcs = dashboard_service.services_at_risk(db, 5)
    resolved = db.scalar(select(func.count()).select_from(Finding).where(Finding.resolved_at >= start)) or 0
    opened = db.scalar(select(func.count()).select_from(Finding).where(Finding.detected_at >= start)) or 0
    return [
        _section("kpis", "Control environment at a glance", _kpis([
            {"label": "Control effectiveness", "value": f"{k['effectiveness_rate']}%"},
            {"label": "Effective instances", "value": f"{k['effective_controls']} / {k['total_control_instances']}"},
            {"label": "Ineffective instances", "value": str(k["failed_controls"])},
            {"label": "Needs review", "value": str(k["needs_review_controls"])},
            {"label": "Critical findings", "value": str(k["critical_findings"])},
            {"label": "Services at risk", "value": f"{k['services_at_risk']} / {k['services_total']}"},
        ])),
        _section("summary", "Summary", {"kind": "bullets", "items": summary.facts},
                 "Generated deterministically from stored assessment and finding records."),
        _section("coverage", "Assessment coverage", _kpis([
            {"label": "Assessment runs", "value": str(cov["runs"])},
            {"label": "Assessments recorded", "value": str(cov["assessments"])},
            {"label": "Instances assessed", "value": f"{cov['assessed_scopes']} / {cov['scopes']}"},
            {"label": "Evidence collected", "value": str(cov["evidence"])},
            {"label": "Findings opened", "value": str(opened)},
            {"label": "Findings resolved", "value": str(resolved)},
        ])),
        _trend_section(db, days),
        _section("top_findings", "Highest-priority unresolved findings",
                 {"kind": "table", "columns": FINDING_COLUMNS, "rows": _findings_rows(top)}),
        _section("services", "Business service exposure", {
            "kind": "table", "columns": ["Service", "Tier", "Unresolved", "Critical", "Exposure index", "Top finding"],
            "rows": [[s["name"], s["tier"], str(s["unresolved_findings"]), str(s["critical_findings"]),
                      f"{s['exposure_index']} ({s['exposure_level']})", s["top_finding"]["ref"] if s["top_finding"] else "—"] for s in svcs]},
            "Exposure index = 0.7 × highest open finding score + 0.3 × mean of top-3. Indicates potential exposure, not confirmed disruption."),
        _section("actions", "Recommended next actions", {"kind": "bullets", "items": _recommendations(db)}),
        _evidence_section(db),
    ]


def _control_effectiveness(db: Session, days: int, start):
    k = dashboard_service.kpis(db)
    rows = []
    for c in db.scalars(select(Control).order_by(Control.id)):
        counts = dict(db.execute(
            select(ControlAssetScope.current_status, func.count()).where(ControlAssetScope.control_id == c.id)
            .group_by(ControlAssetScope.current_status)).all())
        rows.append([c.id, c.name, c.domain, c.current_status, str(counts.get("Effective", 0)),
                     str(counts.get("Ineffective", 0)), str(counts.get("Needs Review", 0)), _d(c.last_assessed_at)])
    failing = []
    for scope in db.scalars(select(ControlAssetScope).where(ControlAssetScope.current_status != "Effective").order_by(ControlAssetScope.control_id)):
        a = db.get(ControlAssessment, scope.latest_assessment_id) if scope.latest_assessment_id else None
        if a:
            failing.append([a.control_id, scope.asset_id, a.result, a.explanation, a.ref])
    return [
        _section("kpis", "Effectiveness overview", _kpis([
            {"label": "Effectiveness rate", "value": f"{k['effectiveness_rate']}%"},
            {"label": "Control definitions", "value": str(k["control_definitions"])},
            {"label": "Definitions failing", "value": str(k["control_definitions_failing"])},
            {"label": "Instances monitored", "value": str(k["total_control_instances"])},
            {"label": "Ineffective", "value": str(k["failed_controls"])},
            {"label": "Needs review", "value": str(k["needs_review_controls"])},
        ])),
        _trend_section(db, days),
        _section("controls", "Control status by definition", {
            "kind": "table", "columns": ["Control", "Name", "Domain", "Status", "Eff.", "Ineff.", "Review", "Last assessed"], "rows": rows}),
        _section("exceptions", "Non-effective control instances", {
            "kind": "table", "columns": ["Control", "Asset", "Result", "Explanation", "Assessment"], "rows": failing}),
        _evidence_section(db),
        _section("actions", "Recommended next actions", {"kind": "bullets", "items": _recommendations(db)}),
    ]


def _critical_findings(db: Session, days: int, start):
    findings = db.scalars(
        select(Finding).where(Finding.status != "Resolved", Finding.severity.in_(("Critical", "High")))
        .order_by(Finding.risk_score.desc())
    ).all()
    crit = [f for f in findings if f.severity == "Critical"]
    details = []
    for f in crit:
        details.append(f"{f.ref} — {f.title}. Impact: {f.business_impact} Recommended remediation: {f.remediation_recommendation}")
    return [
        _section("kpis", "Critical & high findings", _kpis([
            {"label": "Critical (active)", "value": str(len(crit))},
            {"label": "High (active)", "value": str(len(findings) - len(crit))},
            {"label": "Overdue", "value": str(sum(1 for f in findings if f.due_date < utcnow() and f.status in UNRESOLVED_FINDING_STATUSES))},
            {"label": "Risk accepted", "value": str(sum(1 for f in findings if f.status == "Risk Accepted"))},
        ])),
        _section("findings", "Active Critical and High findings", {"kind": "table", "columns": FINDING_COLUMNS, "rows": _findings_rows(findings)}),
        _section("critical_detail", "Critical finding detail", {"kind": "bullets", "items": details or ["No active Critical findings."]}),
        _evidence_section(db),
    ]


def _remediation_aging(db: Session, days: int, start):
    now = utcnow()
    unresolved = db.scalars(select(Finding).where(Finding.status.in_(UNRESOLVED_FINDING_STATUSES))).all()
    buckets = {"0–14 days": 0, "15–30 days": 0, "31–60 days": 0, "Over 60 days": 0}
    for f in unresolved:
        age = (now - f.detected_at).days
        key = "0–14 days" if age <= 14 else "15–30 days" if age <= 30 else "31–60 days" if age <= 60 else "Over 60 days"
        buckets[key] += 1
    resolved = db.scalars(select(Finding).where(Finding.resolved_at >= start)).all()
    mttr = round(sum((f.resolved_at - f.detected_at).days for f in resolved) / len(resolved), 1) if resolved else None
    weeks = []
    for i in range(max(1, days // 7), 0, -1):
        w_end = now - timedelta(days=7 * (i - 1))
        w_start = w_end - timedelta(days=7)
        opened = db.scalar(select(func.count()).select_from(Finding).where(Finding.detected_at >= w_start, Finding.detected_at < w_end)) or 0
        closed = db.scalar(select(func.count()).select_from(Finding).where(Finding.resolved_at >= w_start, Finding.resolved_at < w_end)) or 0
        weeks.append([f"Week ending {_d(w_end)}", str(opened), str(closed)])
    actions = db.scalars(select(RemediationAction).where(RemediationAction.status.in_(("Planned", "In Progress"))).order_by(RemediationAction.due_date)).all()
    accepted = db.scalars(select(Finding).where(Finding.status == "Risk Accepted")).all()
    return [
        _section("kpis", "Remediation performance", _kpis([
            {"label": "Unresolved findings", "value": str(len(unresolved))},
            {"label": "Past due", "value": str(sum(1 for f in unresolved if f.due_date < now))},
            {"label": "Resolved in period", "value": str(len(resolved))},
            {"label": "Mean time to resolve", "value": f"{mttr} days" if mttr is not None else "—"},
        ])),
        _section("aging", "Unresolved finding age", {"kind": "table", "columns": ["Age bucket", "Findings"], "rows": [[k, str(v)] for k, v in buckets.items()]}),
        _section("flow", "Findings opened vs resolved (validated)", {"kind": "table", "columns": ["Week", "Opened", "Resolved"], "rows": weeks}),
        _section("actions_open", "Open remediation actions", {"kind": "table", "columns": ["Action", "Finding", "Title", "Owner", "Status", "Due", "Overdue"],
            "rows": [[a.ref, a.finding.ref, a.title, a.owner.full_name if a.owner else "—", a.status, _d(a.due_date),
                      "Yes" if a.due_date < now else "No"] for a in actions]}),
        _section("acceptances", "Time-bound risk acceptances", {"kind": "table", "columns": ["Finding", "Title", "Approver", "Expires"],
            "rows": [[f.ref, f.title, f.acceptance_approver.full_name if f.acceptance_approver else "—", _d(f.acceptance_expires_at)] for f in accepted]}),
        _section("actions", "Recommended next actions", {"kind": "bullets", "items": _recommendations(db)}),
    ]


def _business_services(db: Session, days: int, start):
    svcs = dashboard_service.services_at_risk(db, 50)
    gctx = load_graph(db)
    spof_rows = []
    for s in svcs:
        if s["tier"] != "Tier 1":
            continue
        for sp in gctx.graph.single_points_of_failure(s["service_id"], gctx.asset_attrs)[:4]:
            spof_rows.append([s["name"], sp["asset_id"], sp["name"], sp["criticality"], str(sp["shared_by_services"])])
    return [
        _section("services", "Service exposure ranking", {
            "kind": "table", "columns": ["Service", "Tier", "Unresolved", "Critical", "Exposure index", "Top finding"],
            "rows": [[s["name"], s["tier"], str(s["unresolved_findings"]), str(s["critical_findings"]),
                      f"{s['exposure_index']} ({s['exposure_level']})",
                      f"{s['top_finding']['ref']} ({s['top_finding']['risk_score']})" if s["top_finding"] else "—"] for s in svcs]},
            "Potential exposure derived from unresolved findings anywhere in each service's dependency path."),
        _section("spof", "Potential single points of failure (Tier 1 services)", {
            "kind": "table", "columns": ["Service", "Asset", "Name", "Criticality", "Services sharing"], "rows": spof_rows},
            "Critical/High dependencies with no documented redundancy."),
        _section("actions", "Recommended next actions", {"kind": "bullets", "items": _recommendations(db)}),
    ]


BUILDERS = {
    "executive_summary": _executive,
    "control_effectiveness": _control_effectiveness,
    "critical_findings": _critical_findings,
    "remediation_aging": _remediation_aging,
    "business_services": _business_services,
}


def build_report(db: Session, report_type: str, period_days: int, user: User | None) -> dict:
    now = utcnow()
    start = now - timedelta(days=period_days)
    sections = BUILDERS[report_type](db, period_days, start)
    return {
        "type": report_type,
        "title": REPORT_TYPES[report_type],
        "organization": get_settings().organization_name,
        "generated_at": now,
        "generated_by": user.full_name if user else "System",
        "period": {"days": period_days, "start": start, "end": now},
        "disclaimer": DISCLAIMER,
        "sections": sections,
    }


# --------------------------------------------------------------------------- PDF rendering
NAVY = colors.HexColor("#0B1F3A")
SLATE = colors.HexColor("#475569")
LIGHT = colors.HexColor("#F1F5F9")
BORDER = colors.HexColor("#CBD5E1")
ACCENT = colors.HexColor("#2563EB")


def render_pdf(report: dict) -> bytes:
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=colors.HexColor("#1E293B"))
    small = ParagraphStyle("small", parent=body, fontSize=7.2, leading=9, textColor=SLATE)
    cell = ParagraphStyle("cell", parent=body, fontSize=7.2, leading=9)
    head = ParagraphStyle("head", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY, spaceBefore=8, spaceAfter=4)
    title = ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.white, alignment=TA_LEFT)

    def on_page(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 30 * mm, w, 30 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(15 * mm, h - 9 * mm, "CONTROLIQ")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w - 15 * mm, h - 9 * mm, report["organization"])
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(15 * mm, h - 19 * mm, report["title"])
        canvas.setFont("Helvetica", 8)
        p = report["period"]
        canvas.drawString(15 * mm, h - 25.5 * mm,
                          f"Reporting period: {_d(p['start'])} – {_d(p['end'])} ({p['days']} days)   |   Generated {report['generated_at'].strftime('%d %b %Y %H:%M UTC')} by {report['generated_by']}")
        canvas.setFillColor(colors.HexColor("#FEF3C7"))
        canvas.rect(0, 10 * mm, w, 7 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#92400E"))
        canvas.setFont("Helvetica", 6.8)
        canvas.drawString(15 * mm, 12.4 * mm, "Synthetic demonstration environment — no production banking data. Fictional entities only.")
        canvas.drawRightString(w - 15 * mm, 12.4 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=36 * mm, bottomMargin=22 * mm,
                            title=report["title"], author="ControlIQ")
    width = A4[0] - 30 * mm
    story = []
    for sec in report["sections"]:
        block = [Paragraph(sec["title"], head)]
        if sec.get("note"):
            block.append(Paragraph(sec["note"], small))
            block.append(Spacer(1, 3))
        kind = sec["kind"]
        if kind == "kpis":
            items = sec["items"]
            per_row = 3
            cells = []
            for i in range(0, len(items), per_row):
                row = []
                for it in items[i:i + per_row]:
                    row.append(Paragraph(f"<font size=7 color='#475569'>{it['label'].upper()}</font><br/>"
                                         f"<font size=14 color='#0B1F3A'><b>{it['value']}</b></font>", body))
                row += [""] * (per_row - len(row))
                cells.append(row)
            t = Table(cells, colWidths=[width / per_row] * per_row)
            t.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
            block.append(t)
        elif kind == "bullets":
            for it in sec["items"]:
                block.append(Paragraph(f"• {_esc(it)}", body))
                block.append(Spacer(1, 2))
        elif kind == "trend":
            pts = [p for p in sec["points"] if p["value"] is not None]
            if len(pts) >= 2:
                block.append(_trend_drawing(pts, width))
            else:
                block.append(Paragraph("Insufficient assessment history in this period.", small))
        elif kind == "table":
            if not sec["rows"]:
                block.append(Paragraph("No records.", small))
            else:
                data = [[Paragraph(f"<b>{_esc(c)}</b>", cell) for c in sec["columns"]]]
                data += [[Paragraph(_esc(str(v)), cell) for v in r] for r in sec["rows"]]
                t = Table(data, colWidths=_col_widths(sec["columns"], width), repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, BORDER), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
                block.append(t)
        story.append(KeepTogether(block[:3]) if kind == "table" else KeepTogether(block))
        if kind == "table":
            story.extend(block[3:])
        story.append(Spacer(1, 6))
    story.append(Spacer(1, 8))
    story.append(Paragraph(_esc(report["disclaimer"]), small))
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _col_widths(columns, width):
    weights = []
    for c in columns:
        lc = c.lower()
        if lc in ("finding", "title", "explanation", "name"):
            weights.append(3.2)
        elif lc in ("service", "owner", "asset", "control", "approver", "domain", "week", "top finding"):
            weights.append(1.6)
        else:
            weights.append(1.0)
    total = sum(weights)
    return [width * w / total for w in weights]


def _trend_drawing(points, width):
    h = 120
    d = Drawing(width, h)
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 30, 20, width - 45, h - 35
    lp.data = [[(i, p["value"]) for i, p in enumerate(points)]]
    lp.lines[0].strokeColor = ACCENT
    lp.lines[0].strokeWidth = 1.6
    vals = [p["value"] for p in points]
    lo = max(0, int(min(vals) // 5 * 5) - 5)
    lp.yValueAxis.valueMin, lp.yValueAxis.valueMax = lo, 100
    lp.yValueAxis.labels.fontSize = 6
    lp.xValueAxis.valueMin, lp.xValueAxis.valueMax = 0, len(points) - 1
    step = max(1, len(points) // 6)
    lp.xValueAxis.valueSteps = list(range(0, len(points), step))
    lp.xValueAxis.labelTextFormat = lambda i: points[int(i)]["label"][:6] if 0 <= int(i) < len(points) else ""
    lp.xValueAxis.labels.fontSize = 6
    d.add(lp)
    d.add(String(0, h - 8, "Effectiveness %", fontSize=6.5, fillColor=SLATE))
    return d


def pdf_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
