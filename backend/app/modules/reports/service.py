"""Report generation (runs in the Celery worker).

Reports are produced with the requester's permissions and scope at generation time.
Complainant personal data appears only when the requester holds ``citizen.read`` AND
explicitly asked for it; every export is audited. The executive summary is a
deterministic narrative composed from the computed figures (no language model).
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.infra import storage
from app.modules.administration.models import Department, IssueCategory
from app.modules.audit import service as audit
from app.modules.geography.models import Block
from app.modules.grievances import service as gsvc
from app.modules.grievances.models import Complainant, Grievance
from app.modules.iam.scope import grievance_scope
from app.modules.iam.service import CurrentUser, user_context
from app.modules.performance import service as perf
from app.modules.reports.models import ReportJob

IST = ZoneInfo("Asia/Kolkata")
TITLES = {
    "grievance_register": "Grievance register",
    "department_performance": "Department performance",
    "block_summary": "Block-wise summary",
    "executive_summary": "Executive summary",
}
MAX_ROWS = 50_000


def _ist(dt: datetime | None) -> str:
    return dt.astimezone(IST).strftime("%d-%m-%Y %H:%M") if dt else ""


def _dt(v: Any) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


def register_rows(db: Session, user: CurrentUser, params: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    f = gsvc.SearchFilters(
        open_only=bool(params.get("open_only")),
        registered_from=_dt(params.get("since")),
        registered_to=_dt(params.get("until")),
        category_id=uuid.UUID(params["category_id"]) if params.get("category_id") else None,
        department_id=uuid.UUID(params["department_id"]) if params.get("department_id") else None,
        block_id=uuid.UUID(params["block_id"]) if params.get("block_id") else None,
    )
    rows, _ = gsvc.list_rows(db, user, f, MAX_ROWS, 0)
    include_pii = bool(params.get("include_pii")) and user.has("citizen.read")
    header = [
        "Reference",
        "Registered (IST)",
        "Subject",
        "Status",
        "Priority",
        "Category",
        "Department",
        "Block",
        "Village",
        "Assigned officer",
        "Due (IST)",
        "Overdue",
        "Risk",
    ]
    if include_pii:
        header += ["Complainant name", "Complainant mobile"]
    out = []
    pii: dict[uuid.UUID, tuple[str | None, str | None]] = {}
    if include_pii:
        ids = [r["id"] for r in rows]
        for gid, c in db.execute(
            select(Grievance.id, Complainant)
            .join(Complainant, Complainant.id == Grievance.complainant_id)
            .where(Grievance.id.in_(ids))
        ).all():
            pii[gid] = (
                security.decrypt_text(c.name_encrypted),
                security.decrypt_text(c.mobile_encrypted),
            )
    for r in rows:
        line = [
            r["reference_no"],
            _ist(r["registered_at"]),
            r["subject"],
            r["status"],
            r["priority"],
            r["category"] or "",
            r["department"] or "",
            r["block"] or "",
            r["village"] or "",
            r["assigned_officer"] or "",
            _ist(r["due_at"]),
            "Yes" if r["overdue"] else "No",
            r["risk_level"] or "",
        ]
        if include_pii:
            line += list(pii.get(r["id"], (None, None)))
        out.append(line)
    return header, out


def perf_rows(db: Session, user: CurrentUser, params: dict[str, Any], by: str) -> tuple[list[str], list[list[Any]]]:
    from app.modules.performance.router import _named

    col, model = (Grievance.department_id, Department) if by == "department" else (Grievance.block_id, Block)
    rows = _named(
        db,
        perf.performance_by(db, col, grievance_scope(user), _dt(params.get("since")), _dt(params.get("until"))),
        model,
    )
    header = [
        by.title(),
        "Received",
        "Open",
        "Resolved",
        "Overdue",
        "SLA compliance %",
        "Resolution rate %",
        "Avg resolution (h)",
        "Reopened",
        "Escalated",
    ]
    return header, [
        [
            r["name"],
            r["received"],
            r["open"],
            r["resolved"],
            r["overdue"],
            r["sla_compliance_pct"] if r["sla_compliance_pct"] is not None else "n/a",
            r["resolution_rate_pct"] if r["resolution_rate_pct"] is not None else "n/a",
            r["avg_hours"] if r["avg_hours"] is not None else "n/a",
            r["reopened"],
            r["escalated"],
        ]
        for r in rows
    ]


def executive_narrative(db: Session, user: CurrentUser, params: dict[str, Any]) -> list[str]:
    since = _dt(params.get("since")) or (datetime.now(UTC) - timedelta(days=30))
    until = _dt(params.get("until")) or datetime.now(UTC)
    tot = perf.performance_by(db, None, grievance_scope(user), since, until)
    t = (
        tot[0]
        if tot
        else {
            "received": 0,
            "open": 0,
            "resolved": 0,
            "overdue": 0,
            "sla_compliance_pct": None,
            "avg_hours": None,
            "reopened": 0,
            "escalated": 0,
        }
    )
    deps = perf_rows(db, user, params | {"since": since.isoformat(), "until": until.isoformat()}, "department")[1]
    cats = perf.performance_by(db, Grievance.category_id, grievance_scope(user), since, until)
    cat_names: dict[Any, Any] = {r[0]: r[1] for r in db.execute(select(IssueCategory.id, IssueCategory.name_en)).all()}
    lines = [
        f"Period: {_ist(since)} to {_ist(until)} (IST). Figures cover grievances within the requesting officer's authorised scope.",
        f"{t['received']} grievances were registered; {t['resolved']} have been resolved and {t['open']} remain open, "
        f"of which {t['overdue']} are past their due time.",
    ]
    if t["sla_compliance_pct"] is not None:
        lines.append(
            f"{t['sla_compliance_pct']}% of resolved grievances with a configured time limit were resolved within it."
        )
    else:
        lines.append("No resolved grievances had a configured time limit, so SLA compliance cannot be stated.")
    if t["avg_hours"] is not None:
        lines.append(f"Average time to resolution was {t['avg_hours']} hours.")
    worst = [d for d in deps if isinstance(d[4], int) and d[4] > 0][:3]
    if worst:
        lines.append(
            "Departments with the most overdue grievances: "
            + "; ".join(f"{d[0]} ({d[4]} overdue of {d[2]} open)" for d in worst)
            + "."
        )
    top = sorted((c for c in cats if c["key"]), key=lambda c: -c["received"])[:3]
    if top:
        lines.append(
            "Most frequent issue categories: "
            + "; ".join(f"{cat_names.get(c['key'], 'Unknown')} ({c['received']})" for c in top)
            + "."
        )
    if t["reopened"] or t["escalated"]:
        lines.append(f"{t['reopened']} grievances were reopened and {t['escalated']} escalated during the period.")
    lines.append(
        "This summary is generated automatically from recorded data. Verify figures before citing them in official communication."
    )
    return lines


def _xlsx(title: str, header: list[str], rows: list[list[Any]], meta_lines: list[str]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    for line in meta_lines:
        ws.append([line])
    ws.append([])
    ws.append(header)
    hdr_row = ws.max_row
    for cell in ws[hdr_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0B2E59")
    for r in rows:
        # Neutralise spreadsheet formula injection from user-supplied text.
        ws.append([("'" + v) if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v for v in r])
    ws.freeze_panes = ws.cell(row=hdr_row + 1, column=1)
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None and c.row >= hdr_row), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 60)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf(
    title: str,
    header: list[str],
    rows: list[list[Any]],
    meta_lines: list[str],
    narrative: list[str] | None,
) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=title,
        author="DG-IMEWS",
    )
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=7, leading=8.5)
    story: list[Any] = [Paragraph(escape(title), ss["Title"])]
    story += [Paragraph(escape(m), ss["BodyText"]) for m in meta_lines]
    story.append(Spacer(1, 4 * mm))
    for line in narrative or []:
        story.append(Paragraph(escape(line), ss["BodyText"]))
        story.append(Spacer(1, 2 * mm))
    if header:
        data = [[Paragraph(f"<b>{escape(h)}</b>", small) for h in header]]
        data += [[Paragraph(escape(str(v)), small) for v in r] for r in rows[:5000]]
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3EAF4")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#6B737C")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(tbl)
        if len(rows) > 5000:
            story.append(
                Paragraph(
                    f"Showing the first 5000 of {len(rows)} rows. Use the Excel format for the full list.",
                    ss["Italic"],
                )
            )

    def footer(canvas: Any, d: Any) -> None:
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            12 * mm,
            7 * mm,
            f"DG-IMEWS - for official use - generated {_ist(datetime.now(UTC))} IST",
        )
        canvas.drawRightString(d.pagesize[0] - 12 * mm, 7 * mm, f"Page {d.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def generate(db: Session, job_id: uuid.UUID) -> ReportJob:
    job = db.get(ReportJob, job_id, with_for_update=True)
    if job is None or job.status not in ("queued", "failed"):
        return job  # type: ignore[return-value]
    job.status, job.started_at = "running", datetime.now(UTC)
    db.flush()
    savepoint = db.begin_nested()
    try:
        user = user_context(db, job.requested_by)
        p = job.parameters
        title = TITLES[job.report_type]
        settings = get_settings()
        meta_lines = [
            f"{settings.deployment_district_name or 'District'}: generated {_ist(datetime.now(UTC))} IST for "
            f"{user.full_name} ({user.username}).",
            "Scope: grievances within the requester's authorised area. Contains official information.",
        ]
        narrative = None
        if job.report_type == "grievance_register":
            header, rows = register_rows(db, user, p)
            if p.get("include_pii") and user.has("citizen.read"):
                meta_lines.append(
                    "CONTAINS PERSONAL DATA of complainants. Handle under applicable data-protection rules."
                )
        elif job.report_type == "department_performance":
            header, rows = perf_rows(db, user, p, "department")
        elif job.report_type == "block_summary":
            header, rows = perf_rows(db, user, p, "block")
        else:
            narrative = executive_narrative(db, user, p)
            header, rows = perf_rows(db, user, p, "department")
        data = (
            _xlsx(title, header, rows, meta_lines + (narrative or []))
            if job.format == "xlsx"
            else _pdf(title, header, rows, meta_lines, narrative)
        )
        key = f"reports/{job.id}.{job.format}"
        storage.put_bytes(
            key,
            data,
            "application/pdf"
            if job.format == "pdf"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        job.storage_key, job.row_count = key, len(rows)
        job.filename = f"{job.report_type}_{datetime.now(IST).strftime('%Y%m%d_%H%M')}.{job.format}"
        job.status, job.completed_at = "completed", datetime.now(UTC)
        job.expires_at = job.completed_at + timedelta(days=7)
        audit.record(
            db,
            action="report.generated",
            actor=user.actor,
            resource_type="report",
            resource_id=job.id,
            details={
                "type": job.report_type,
                "format": job.format,
                "rows": len(rows),
                "includes_pii": bool(p.get("include_pii") and user.has("citizen.read")),
            },
        )
        savepoint.commit()
    except Exception as exc:
        savepoint.rollback()
        refreshed = db.get(ReportJob, job_id)
        assert refreshed is not None
        job = refreshed
        job.status, job.error = "failed", f"{type(exc).__name__}: report generation failed"
        import logging

        logging.getLogger("app.reports").exception("report_failed", extra={"job_id": str(job.id)})
    return job
