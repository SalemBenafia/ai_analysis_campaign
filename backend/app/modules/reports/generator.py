"""
app/modules/reports/generator.py — PDF report generation using ReportLab.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

import structlog
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

logger = structlog.get_logger()

_BG = colors.HexColor("#0a0f1f")
_ACCENT = colors.HexColor("#00d4ff")
_WHITE = colors.white
_MUTED = colors.HexColor("#a0b0cc")


def generate_report_pdf(
    report_name: str,
    dataset_name: str,
    kpis: dict[str, Any],
    top_performers: list[dict],
    insights: list[str],
    generated_at: datetime | None = None,
) -> bytes:
    """Generate a branded InsightAI PDF report. Returns PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=24, textColor=_ACCENT, spaceAfter=12)
    heading_style = ParagraphStyle("heading", parent=styles["Heading2"], fontSize=14, textColor=_ACCENT, spaceAfter=8)
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, textColor=colors.black, spaceAfter=6)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=_MUTED, spaceAfter=4)

    elements = []

    elements.append(Paragraph(f"InsightAI — {report_name}", title_style))
    elements.append(Paragraph(f"Dataset: {dataset_name}", sub_style))
    ts = (generated_at or datetime.now(tz=timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    elements.append(Paragraph(f"Generated: {ts}", sub_style))
    elements.append(HRFlowable(width="100%", color=_ACCENT, thickness=1, spaceAfter=12))
    elements.append(Spacer(1, 0.2 * inch))

    if kpis:
        elements.append(Paragraph("Key Performance Indicators", heading_style))
        kpi_data = [["Metric", "Value"]] + [
            [k.replace("_", " ").title(), f"{v:,.2f}" if isinstance(v, float) else str(v)]
            for k, v in list(kpis.items())[:10]
        ]
        kpi_table = Table(kpi_data, colWidths=[3 * inch, 2 * inch])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("GRID", (0, 0), (-1, -1), 0.5, _MUTED),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 0.3 * inch))

    if top_performers:
        elements.append(Paragraph("Top Performers", heading_style))
        fields = list(top_performers[0].keys()) if top_performers else []
        tp_data = [fields] + [[str(r.get(f, "")) for f in fields] for r in top_performers[:10]]
        tp_table = Table(tp_data)
        tp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("GRID", (0, 0), (-1, -1), 0.5, _MUTED),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(tp_table)
        elements.append(Spacer(1, 0.3 * inch))

    if insights:
        elements.append(Paragraph("AI Insights & Recommendations", heading_style))
        for i, insight in enumerate(insights, 1):
            elements.append(Paragraph(f"{i}. {insight}", body_style))

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_MUTED)
        canvas.drawCentredString(letter[0] / 2, 0.5 * inch, f"InsightAI — Page {doc.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
