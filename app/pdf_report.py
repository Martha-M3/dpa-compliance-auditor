"""
The audit summary as a real PDF file (IR-06), built on the server with ReportLab.

It shows the same figures as the printable summary page: score, executive summary, score breakdown,
violations by severity, policy alignment and recommendations. The text comes from the dictionary that
reports.build_summary() returns, so the page and the PDF can never disagree.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

TEAL = colors.HexColor("#0F766E")
GREY = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
TONES = {"good": colors.HexColor("#059669"), "warn": colors.HexColor("#D97706"), "bad": colors.HexColor("#DC2626"), "muted": GREY}


def _styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("brand", parent=base["Normal"], fontSize=9, textColor=TEAL, fontName="Helvetica-Bold"),
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=20, leading=24, alignment=0, spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=9, textColor=GREY, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, textColor=TEAL, spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=9, leading=12),
        "head": ParagraphStyle("head", parent=base["Normal"], fontSize=9, leading=12, fontName="Helvetica-Bold"),
        "foot": ParagraphStyle("foot", parent=base["Normal"], fontSize=8, textColor=GREY, leading=11),
    }


def _p(text, style):
    return Paragraph(escape(str(text)), style)


def _table(rows, widths, styles):
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_pdf(summary):
    """Return the PDF bytes for one audit summary."""
    st = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=f"{summary['code']} Audit Summary", author="KenyaDPA Audit")
    width = A4[0] - 40 * mm
    story = [
        _p("KenyaDPA Audit", st["brand"]),
        _p("Kenya DPA (2019) Audit Summary", st["title"]),
        _p(f"{summary['code']}  |  {summary['file_name']}  |  Audited {summary['date']}  |  Run by {summary['run_by']}", st["sub"]),
    ]

    tone = TONES.get(summary["tone"], GREY)
    score = f"{summary['score']}%" if summary["score"] is not None else "-"
    records = f"{summary['total_records']:,}" if summary["total_records"] is not None else "-"
    facts = Table([
        [_p("COMPLIANCE SCORE", st["foot"]), _p("STATUS", st["foot"]), _p("RECORDS", st["foot"]), _p("VIOLATIONS", st["foot"]), _p("RECORDS AFFECTED", st["foot"])],
        [Paragraph(f'<font size="20" color="{tone.hexval()}"><b>{escape(score)}</b></font>', st["body"]),
         Paragraph(f'<font color="{tone.hexval()}"><b>{escape(summary["status"])}</b></font>', st["body"]),
         _p(records, st["body"]), _p(f"{summary['violations']:,}", st["body"]), _p(f"{summary['violating_records']:,}", st["body"])],
    ], colWidths=[width * f for f in (0.24, 0.26, 0.16, 0.16, 0.18)])
    facts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 1), (-1, 1), 0.5, LINE), ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE)]))
    story += [facts, _p("Executive Summary", st["h2"]), _p(summary["executive"], st["body"])]

    story.append(_p("Score Breakdown", st["h2"]))
    rows = [[_p(h, st["head"]) for h in ("DPA category", "Score", "Risk", "Violations")]]
    for item in summary["breakdown"]:
        rows.append([_p(item["label"], st["cell"]), _p(f"{item['score']}%" if item["score"] is not None else "-", st["cell"]),
                     _p(item["risk"] or "-", st["cell"]), _p(f"{item['violations']:,}", st["cell"])])
    story.append(_table(rows, [width * f for f in (0.4, 0.15, 0.25, 0.2)], st))

    story.append(_p("Violations by Severity", st["h2"]))
    names, counts = zip(*summary["severity_counts"])
    story.append(_table([[_p(n, st["head"]) for n in names], [_p(f"{c:,}", st["cell"]) for c in counts]], [width / len(names)] * len(names), st))

    story.append(_p("Policy Alignment", st["h2"]))
    if summary.get("policy"):
        rows = [[_p(h, st["head"]) for h in ("DPA topic", "Result", "Closest policy statement")]]
        for item in summary["policy"]:
            quote = f"“{item['statement']}”" if item["statement"] else "No statement in the policy matches this topic."
            rows.append([_p(item["category"], st["cell"]), _p(item["verdict"], st["cell"]), _p(quote, st["cell"])])
        story.append(_table(rows, [width * f for f in (0.22, 0.2, 0.58)], st))
    else:
        story.append(_p("No policy document was compared when this audit ran.", st["body"]))

    story.append(_p("Key Recommendations", st["h2"]))
    if summary["recommendations"]:
        for text in summary["recommendations"]:
            story.append(Paragraph(f"• {escape(text)}", st["body"]))
    else:
        story.append(_p("No action is needed. Run the audit again after the next data update.", st["body"]))

    story += [Spacer(1, 14), _p("Generated automatically by the DPA Compliance Auditing System. These findings come from automated "
                                "rules and should be reviewed by a qualified person before action is taken.", st["foot"])]
    doc.build(story)
    return buffer.getvalue()
