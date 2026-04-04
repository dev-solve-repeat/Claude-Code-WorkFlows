"""
Tool: generate_pdf.py
Purpose: Generate a branded PDF competitor analysis report for Xpatz Global.
Output: competitor_analysis_YYYY-MM-DD.pdf
"""

import json
import os
import argparse
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether,
)
from reportlab.platypus.flowables import Flowable
from dotenv import load_dotenv

load_dotenv()

# ─── Brand Colors ───────────────────────────────────────────────────────────
PRIMARY    = HexColor("#1A1A1A")   # Near-black (matches logo)
ACCENT     = HexColor("#C9A84C")   # Gold accent
LIGHT_BG   = HexColor("#F5F5F5")   # Section backgrounds
MID_GRAY   = HexColor("#888888")   # Subtext
DARK_GRAY  = HexColor("#333333")   # Body text
GREEN      = HexColor("#2E7D32")   # Strength / positive
RED        = HexColor("#C62828")   # Weakness / negative
AMBER      = HexColor("#F57F17")   # Medium priority
BLUE_DARK  = HexColor("#1565C0")   # High priority badge

PAGE_W, PAGE_H = A4


# ─── Helper Flowable: Full-Width Color Bar ───────────────────────────────────
class ColorBar(Flowable):
    def __init__(self, width, height, color):
        super().__init__()
        self.width = width
        self.height = height
        self.color = color

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)


# ─── Style Definitions ───────────────────────────────────────────────────────
def build_styles():
    base = getSampleStyleSheet()

    styles = {}
    styles["cover_title"] = ParagraphStyle(
        "cover_title", fontSize=32, textColor=white, alignment=TA_CENTER,
        fontName="Helvetica-Bold", spaceAfter=10, leading=38,
    )
    styles["cover_subtitle"] = ParagraphStyle(
        "cover_subtitle", fontSize=14, textColor=ACCENT, alignment=TA_CENTER,
        fontName="Helvetica", spaceAfter=6, leading=18,
    )
    styles["cover_date"] = ParagraphStyle(
        "cover_date", fontSize=11, textColor=HexColor("#CCCCCC"), alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
    )
    styles["cover_confidential"] = ParagraphStyle(
        "cover_confidential", fontSize=8, textColor=HexColor("#999999"), alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
    )
    styles["section_header"] = ParagraphStyle(
        "section_header", fontSize=18, textColor=white, alignment=TA_LEFT,
        fontName="Helvetica-Bold", leading=22, leftIndent=12,
    )
    styles["subsection_header"] = ParagraphStyle(
        "subsection_header", fontSize=13, textColor=PRIMARY, alignment=TA_LEFT,
        fontName="Helvetica-Bold", spaceAfter=4, spaceBefore=8, leading=16,
    )
    styles["body"] = ParagraphStyle(
        "body", fontSize=9.5, textColor=DARK_GRAY, alignment=TA_JUSTIFY,
        fontName="Helvetica", leading=14, spaceAfter=4,
    )
    styles["body_small"] = ParagraphStyle(
        "body_small", fontSize=8.5, textColor=DARK_GRAY, fontName="Helvetica", leading=12,
    )
    styles["bullet"] = ParagraphStyle(
        "bullet", fontSize=9, textColor=DARK_GRAY, fontName="Helvetica",
        leftIndent=12, bulletIndent=0, leading=13, spaceAfter=2,
    )
    styles["label"] = ParagraphStyle(
        "label", fontSize=8, textColor=MID_GRAY, fontName="Helvetica-Bold",
        spaceAfter=2, leading=10,
    )
    styles["value"] = ParagraphStyle(
        "value", fontSize=9, textColor=DARK_GRAY, fontName="Helvetica", leading=12,
    )
    styles["gold_italic"] = ParagraphStyle(
        "gold_italic", fontSize=9, textColor=ACCENT, fontName="Helvetica-Oblique",
        leading=13, spaceAfter=4,
    )
    styles["toc_item"] = ParagraphStyle(
        "toc_item", fontSize=10, textColor=DARK_GRAY, fontName="Helvetica",
        leading=16, leftIndent=8,
    )
    styles["page_footer"] = ParagraphStyle(
        "page_footer", fontSize=7.5, textColor=MID_GRAY, fontName="Helvetica",
    )
    styles["card_heading"] = ParagraphStyle(
        "card_heading", fontSize=10, textColor=PRIMARY, fontName="Helvetica-Bold",
        leading=13, spaceAfter=3,
    )
    return styles


# ─── Page Template with Footer ───────────────────────────────────────────────
def make_footer_callback(logo_path: str, report_date: str, company_name: str):
    def on_page(canvas, doc):
        if doc.page == 1:
            return  # No footer on cover
        canvas.saveState()

        # Footer line
        canvas.setStrokeColor(HexColor("#DDDDDD"))
        canvas.setLineWidth(0.5)
        canvas.line(inch * 0.75, 0.65 * inch, PAGE_W - inch * 0.75, 0.65 * inch)

        # Left: small logo or company name
        if logo_path and os.path.exists(logo_path):
            try:
                canvas.drawImage(
                    logo_path, inch * 0.75, 0.35 * inch,
                    width=0.8 * inch, height=0.25 * inch,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception:
                canvas.setFont("Helvetica-Bold", 7)
                canvas.setFillColor(PRIMARY)
                canvas.drawString(inch * 0.75, 0.42 * inch, company_name)
        else:
            canvas.setFont("Helvetica-Bold", 7)
            canvas.setFillColor(PRIMARY)
            canvas.drawString(inch * 0.75, 0.42 * inch, company_name)

        # Center: page number
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MID_GRAY)
        page_text = f"Page {doc.page}"
        canvas.drawCentredString(PAGE_W / 2, 0.42 * inch, page_text)

        # Right: date
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MID_GRAY)
        canvas.drawRightString(PAGE_W - inch * 0.75, 0.42 * inch, report_date)

        canvas.restoreState()

    return on_page


# ─── Section Header Block ────────────────────────────────────────────────────
def section_header(title: str, styles: dict, width: float = None) -> list:
    w = width or (PAGE_W - 2.2 * cm)
    bar = ColorBar(w, 0.45 * inch, PRIMARY)
    para = Paragraph(title, styles["section_header"])
    # Overlay text on bar using a table
    table = Table([[para]], colWidths=[w], rowHeights=[0.45 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [Spacer(1, 8), table, Spacer(1, 10)]


# ─── Cover Page ─────────────────────────────────────────────────────────────
def build_cover(logo_path: str, company_name: str, report_date: str, n_competitors: int, styles: dict) -> list:
    elements = []

    # Dark full-page background via a large table
    cover_table = Table(
        [[""]], colWidths=[PAGE_W], rowHeights=[PAGE_H],
    )
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
    ]))

    # We simulate the cover using a sequence of centered elements on a dark page
    # Use a framed background approach by drawing on canvas (handled in on_page)
    # Instead, build a tall table that fills the page
    content_rows = []

    # Top spacer
    content_rows.append([Spacer(1, 1.5 * inch)])

    # Logo
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=2.8 * inch, height=1.4 * inch)
            logo.hAlign = "CENTER"
            content_rows.append([logo])
        except Exception:
            pass

    content_rows.append([Spacer(1, 0.4 * inch)])

    # Title
    content_rows.append([Paragraph("Competitor Intelligence Report", styles["cover_title"])])
    content_rows.append([Spacer(1, 0.15 * inch)])
    content_rows.append([Paragraph("Immigration &amp; Visa Consultancy — European Work Permits", styles["cover_subtitle"])])
    content_rows.append([Spacer(1, 0.4 * inch)])

    # Divider line (accent color)
    hr_table = Table([[""]], colWidths=[3 * inch], rowHeights=[2])
    hr_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT)]))
    hr_table.hAlign = "CENTER"
    content_rows.append([hr_table])
    content_rows.append([Spacer(1, 0.4 * inch)])

    # Stats
    content_rows.append([Paragraph(f"Prepared: {report_date}", styles["cover_date"])])
    content_rows.append([Spacer(1, 0.1 * inch)])
    content_rows.append([Paragraph(f"Competitors Analyzed: {n_competitors}", styles["cover_date"])])
    content_rows.append([Spacer(1, 0.1 * inch)])
    content_rows.append([Paragraph("Prepared for: Xpatz Global — Internal Use", styles["cover_date"])])

    # Bottom spacer + confidential notice
    content_rows.append([Spacer(1, 2.5 * inch)])
    content_rows.append([Paragraph(
        "CONFIDENTIAL — This report is for internal use only. Do not distribute.",
        styles["cover_confidential"],
    )])

    cover = Table(content_rows, colWidths=[PAGE_W - 2 * cm])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    elements.append(cover)
    elements.append(PageBreak())
    return elements


# ─── Executive Summary ───────────────────────────────────────────────────────
def build_executive_summary(analysis: dict, styles: dict) -> list:
    elements = section_header("Executive Summary", styles)

    n = analysis.get("competitors_analyzed", 0)
    gaps = analysis.get("gaps_and_opportunities", [])
    recs = analysis.get("recommendations", [])

    summary_text = (
        f"This report analyzes <b>{n} competitors</b> in the immigration and visa consultancy space, "
        f"with a focus on companies offering European work permits and visa services to Indian workers. "
        f"The analysis covers pricing, services, marketing messaging, and customer sentiment gathered "
        f"from publicly available sources."
    )
    elements.append(Paragraph(summary_text, styles["body"]))
    elements.append(Spacer(1, 8))

    if gaps:
        top_gap = gaps[0]
        elements.append(Paragraph(
            f"<b>Key Opportunity:</b> {top_gap.get('gap', '')} — {top_gap.get('opportunity', '')}",
            styles["body"],
        ))
        elements.append(Spacer(1, 8))

    if recs:
        high_recs = [r for r in recs if r.get("priority") == "high"]
        if high_recs:
            elements.append(Paragraph(
                f"<b>Top Priority Action:</b> {high_recs[0].get('recommendation', '')}",
                styles["body"],
            ))
            elements.append(Spacer(1, 8))

    # Stats box
    stats_data = [
        [
            Paragraph("<b>Competitors Analyzed</b>", styles["label"]),
            Paragraph("<b>Opportunities Found</b>", styles["label"]),
            Paragraph("<b>Recommendations</b>", styles["label"]),
        ],
        [
            Paragraph(str(n), ParagraphStyle("stat_num", fontSize=22, textColor=PRIMARY,
                                             fontName="Helvetica-Bold", alignment=TA_CENTER)),
            Paragraph(str(len(gaps)), ParagraphStyle("stat_num2", fontSize=22, textColor=ACCENT,
                                                      fontName="Helvetica-Bold", alignment=TA_CENTER)),
            Paragraph(str(len(recs)), ParagraphStyle("stat_num3", fontSize=22, textColor=GREEN,
                                                      fontName="Helvetica-Bold", alignment=TA_CENTER)),
        ],
    ]
    col_w = (PAGE_W - 2.2 * cm) / 3
    stats_table = Table(stats_data, colWidths=[col_w] * 3, rowHeights=[20, 40])
    stats_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#DDDDDD")),
    ]))
    elements.append(Spacer(1, 10))
    elements.append(stats_table)
    elements.append(PageBreak())
    return elements


# ─── Competitor Profiles ─────────────────────────────────────────────────────
def sentiment_color(sentiment: str) -> HexColor:
    return {
        "positive": GREEN,
        "negative": RED,
        "mixed": AMBER,
    }.get(sentiment, MID_GRAY)


def star_string(score) -> str:
    if score is None:
        return "N/A"
    try:
        score = float(score)
        filled = int(round(score))
        return "★" * filled + "☆" * (5 - filled) + f"  {score:.1f}/5"
    except Exception:
        return str(score)


def build_competitor_profiles(analysis: dict, styles: dict) -> list:
    elements = section_header("Competitor Profiles", styles)
    profiles = analysis.get("competitor_profiles", [])

    if not profiles:
        elements.append(Paragraph("No competitor profiles available.", styles["body"]))
        elements.append(PageBreak())
        return elements

    col_w = (PAGE_W - 2.2 * cm) / 2

    for i, profile in enumerate(profiles):
        name = profile.get("name", "Unknown")
        website = profile.get("website", "")
        pricing_tier = profile.get("pricing_tier", "unknown")
        pricing_detail = profile.get("pricing_detail", "Not available") or "Not available"
        key_messaging = profile.get("key_messaging", "Not available") or "Not available"
        target_audience = profile.get("target_audience", "Not specified") or "Not specified"
        review_sentiment = profile.get("review_sentiment", "unknown")
        review_score = profile.get("review_score")
        notable_themes = profile.get("notable_review_themes", [])
        services = profile.get("services", [])
        strengths = profile.get("strengths", [])
        weaknesses = profile.get("weaknesses", [])
        digital_presence = profile.get("digital_presence", "unknown")

        # Competitor header bar (accent color)
        comp_header_table = Table(
            [[Paragraph(f"{i + 1}. {name}", ParagraphStyle(
                "comp_name", fontSize=14, textColor=white,
                fontName="Helvetica-Bold", leading=18,
            ))]],
            colWidths=[PAGE_W - 2.2 * cm],
            rowHeights=[0.38 * inch],
        )
        comp_header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))

        # Info row: website | pricing tier | digital presence | sentiment
        info_data = [
            [
                Paragraph(f"<b>Website:</b> {website[:45]}", styles["body_small"]),
                Paragraph(f"<b>Pricing:</b> {pricing_tier.title()}", styles["body_small"]),
                Paragraph(f"<b>Digital:</b> {digital_presence.title()}", styles["body_small"]),
                Paragraph(f"<b>Sentiment:</b> {review_sentiment.title()}", styles["body_small"]),
            ]
        ]
        info_col_w = (PAGE_W - 2.2 * cm) / 4
        info_table = Table(info_data, colWidths=[info_col_w] * 4, rowHeights=[22])
        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, HexColor("#DDDDDD")),
        ]))

        # 2×2 detail grid
        services_text = "\n".join(f"• {s}" for s in services[:6]) or "Not available"
        pricing_text = f"{pricing_detail}\n\nTier: {pricing_tier.title()}"
        messaging_text = f"{key_messaging}\n\nTarget: {target_audience}"
        reviews_text = f"{star_string(review_score)}\n{review_sentiment.title()}"
        if notable_themes:
            reviews_text += "\n\n" + "\n".join(f"• {t}" for t in notable_themes[:4])

        grid_data = [
            [
                Paragraph("<b>Services Offered</b>", styles["card_heading"]),
                Paragraph("<b>Pricing &amp; Offers</b>", styles["card_heading"]),
            ],
            [
                Paragraph(services_text, styles["body_small"]),
                Paragraph(pricing_text, styles["body_small"]),
            ],
            [
                Paragraph("<b>Marketing &amp; Messaging</b>", styles["card_heading"]),
                Paragraph("<b>Reviews &amp; Sentiment</b>", styles["card_heading"]),
            ],
            [
                Paragraph(messaging_text, styles["body_small"]),
                Paragraph(reviews_text, styles["body_small"]),
            ],
        ]
        grid_table = Table(
            grid_data,
            colWidths=[col_w, col_w],
            rowHeights=[18, 70, 18, 70],
        )
        grid_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), white),
            ("BACKGROUND", (0, 0), (1, 0), LIGHT_BG),
            ("BACKGROUND", (0, 2), (1, 2), LIGHT_BG),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#DDDDDD")),
        ]))

        # Strengths / Weaknesses table
        max_sw = max(len(strengths), len(weaknesses), 1)
        sw_rows = []
        for j in range(max_sw):
            s = strengths[j] if j < len(strengths) else ""
            w = weaknesses[j] if j < len(weaknesses) else ""
            sw_rows.append([
                Paragraph(f"✓ {s}" if s else "", styles["body_small"]),
                Paragraph(f"✗ {w}" if w else "", styles["body_small"]),
            ])

        sw_table = Table(
            [
                [
                    Paragraph("STRENGTHS", ParagraphStyle("sw_h", fontSize=8, textColor=white,
                                                           fontName="Helvetica-Bold", alignment=TA_CENTER)),
                    Paragraph("WEAKNESSES", ParagraphStyle("sw_h2", fontSize=8, textColor=white,
                                                            fontName="Helvetica-Bold", alignment=TA_CENTER)),
                ]
            ] + sw_rows,
            colWidths=[col_w, col_w],
        )
        sw_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), GREEN),
            ("BACKGROUND", (1, 0), (1, 0), RED),
            ("BACKGROUND", (0, 1), (0, -1), HexColor("#F1F8F1")),
            ("BACKGROUND", (1, 1), (1, -1), HexColor("#FFF1F1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#DDDDDD")),
            ("ROWHEIGHT", (0, 0), (0, 0), 18),
        ]))

        block = KeepTogether([
            comp_header_table,
            info_table,
            grid_table,
            sw_table,
            Spacer(1, 14),
        ])
        elements.append(block)

        if (i + 1) % 2 == 0 and i < len(profiles) - 1:
            elements.append(PageBreak())

    elements.append(PageBreak())
    return elements


# ─── Positioning Matrix ──────────────────────────────────────────────────────
RATING_COLORS = {
    "high": HexColor("#C8E6C9"),
    "very high": HexColor("#A5D6A7"),
    "strong": HexColor("#C8E6C9"),
    "low": HexColor("#FFCDD2"),
    "weak": HexColor("#FFCDD2"),
    "moderate": HexColor("#FFF9C4"),
    "mixed": HexColor("#FFF9C4"),
    "unknown": HexColor("#F5F5F5"),
    "premium": HexColor("#FFCDD2"),
    "mid-range": HexColor("#FFF9C4"),
    "budget": HexColor("#C8E6C9"),
    "positive": HexColor("#C8E6C9"),
    "negative": HexColor("#FFCDD2"),
}


def rating_cell(value: str, styles: dict) -> Paragraph:
    color = RATING_COLORS.get(str(value).lower(), HexColor("#F5F5F5"))
    # We set background via table style, just return the text
    return Paragraph(str(value).title() if value else "—", styles["body_small"])


def build_positioning_matrix(analysis: dict, styles: dict) -> list:
    elements = section_header("Competitive Positioning Matrix", styles)

    matrix = analysis.get("positioning_matrix", [])
    if not matrix:
        elements.append(Paragraph("Positioning matrix data not available.", styles["body"]))
        elements.append(PageBreak())
        return elements

    headers = ["Competitor", "Services", "Pricing", "Digital", "Rating", "Europe Focus", "Blue Collar", "India Presence"]
    header_row = [Paragraph(f"<b>{h}</b>", styles["body_small"]) for h in headers]

    col_widths = [1.6 * inch, 0.7 * inch, 0.75 * inch, 0.65 * inch, 0.6 * inch, 0.8 * inch, 0.8 * inch, 0.9 * inch]

    table_data = [header_row]
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    for row_idx, comp in enumerate(matrix, start=1):
        score = comp.get("review_score")
        try:
            score_text = f"{float(score):.1f}" if score and score != "N/A" else "—"
        except (ValueError, TypeError):
            score_text = str(score) if score else "—"
        row = [
            Paragraph(f"<b>{comp.get('competitor', '—')}</b>", styles["body_small"]),
            Paragraph(comp.get("service_breadth", "—").title(), styles["body_small"]),
            Paragraph(comp.get("pricing", "—").title(), styles["body_small"]),
            Paragraph(comp.get("digital_presence", "—").title(), styles["body_small"]),
            Paragraph(score_text, styles["body_small"]),
            Paragraph(comp.get("europe_specialization", "—").title(), styles["body_small"]),
            Paragraph(comp.get("blue_collar_focus", "—").title(), styles["body_small"]),
            Paragraph(comp.get("india_market_presence", "—").title(), styles["body_small"]),
        ]
        table_data.append(row)

        # Row shading
        bg = HexColor("#F9F9F9") if row_idx % 2 == 0 else white
        style_cmds.append(("BACKGROUND", (0, row_idx), (0, row_idx), LIGHT_BG))

        # Color-code key cells
        field_col_map = [
            ("service_breadth", 1),
            ("pricing", 2),
            ("digital_presence", 3),
            ("europe_specialization", 5),
            ("blue_collar_focus", 6),
            ("india_market_presence", 7),
        ]
        for field, col in field_col_map:
            val = comp.get(field, "").lower()
            cell_color = RATING_COLORS.get(val, bg)
            style_cmds.append(("BACKGROUND", (col, row_idx), (col, row_idx), cell_color))

    matrix_table = Table(table_data, colWidths=col_widths)
    matrix_table.setStyle(TableStyle(style_cmds))

    elements.append(matrix_table)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        "<i>Color coding: Green = favorable, Yellow = moderate, Red = unfavorable/premium pricing</i>",
        styles["body_small"],
    ))
    elements.append(PageBreak())
    return elements


# ─── What Competitors Do Well ────────────────────────────────────────────────
def build_doing_well(analysis: dict, styles: dict) -> list:
    elements = section_header("What Competitors Are Doing Well", styles)

    observations = analysis.get("what_competitors_do_well", [])
    if not observations:
        elements.append(Paragraph("No observations available.", styles["body"]))
        elements.append(PageBreak())
        return elements

    for i, obs in enumerate(observations):
        observation = obs.get("observation", "")
        competitors = ", ".join(obs.get("competitors", []))
        implication = obs.get("implication_for_xpatz", "")

        card_data = [
            [Paragraph(f"<b>{i + 1}. {observation}</b>", styles["card_heading"])],
        ]
        if competitors:
            card_data.append([Paragraph(f"Seen at: {competitors}", styles["body_small"])])
        if implication:
            card_data.append([Paragraph(f"Implication for Xpatz: {implication}", styles["gold_italic"])])

        card = Table(card_data, colWidths=[PAGE_W - 2.2 * cm])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBEfore", (0, 0), (0, -1), 4, ACCENT),
            ("ROUNDEDCORNERS", [3, 3, 3, 3]),
        ]))
        elements.append(card)
        elements.append(Spacer(1, 8))

    elements.append(PageBreak())
    return elements


# ─── Gaps & Opportunities ────────────────────────────────────────────────────
def build_gaps(analysis: dict, styles: dict) -> list:
    elements = section_header("Gaps &amp; Opportunities for Xpatz Global", styles)

    gaps = analysis.get("gaps_and_opportunities", [])
    if not gaps:
        elements.append(Paragraph("No gaps identified.", styles["body"]))
        elements.append(PageBreak())
        return elements

    for i, gap in enumerate(gaps):
        gap_text = gap.get("gap", "")
        evidence = gap.get("evidence", "")
        opportunity = gap.get("opportunity", "")

        # Number badge
        badge = Table(
            [[Paragraph(str(i + 1), ParagraphStyle(
                "badge_num", fontSize=11, textColor=white,
                fontName="Helvetica-Bold", alignment=TA_CENTER,
            ))]],
            colWidths=[0.3 * inch],
            rowHeights=[0.3 * inch],
        )
        badge.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))

        content_col_w = PAGE_W - 2.2 * cm - 0.4 * inch
        content_data = []
        if gap_text:
            content_data.append([Paragraph(f"<b>Gap:</b> {gap_text}", styles["body"])])
        if evidence:
            content_data.append([Paragraph(f"<b>Evidence:</b> {evidence}", styles["body_small"])])
        if opportunity:
            content_data.append([Paragraph(f"<b>Opportunity:</b> {opportunity}", ParagraphStyle(
                "opp", fontSize=9.5, textColor=PRIMARY, fontName="Helvetica-Bold",
                leading=14, spaceAfter=0,
            ))])

        content_table = Table(content_data, colWidths=[content_col_w])
        content_table.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))

        row_table = Table(
            [[badge, content_table]],
            colWidths=[0.4 * inch, content_col_w],
        )
        row_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, -1), 1, ACCENT),
        ]))
        elements.append(row_table)
        elements.append(Spacer(1, 8))

    elements.append(PageBreak())
    return elements


# ─── Recommendations ─────────────────────────────────────────────────────────
PRIORITY_COLORS = {
    "high": (BLUE_DARK, "HIGH"),
    "medium": (AMBER, "MEDIUM"),
    "low": (MID_GRAY, "LOW"),
}


def build_recommendations(analysis: dict, styles: dict) -> list:
    elements = section_header("Strategic Recommendations", styles)

    recs = analysis.get("recommendations", [])
    if not recs:
        elements.append(Paragraph("No recommendations available.", styles["body"]))
        elements.append(PageBreak())
        return elements

    for rec in recs:
        priority = rec.get("priority", "medium").lower()
        recommendation = rec.get("recommendation", "")
        rationale = rec.get("rationale", "")
        effort = rec.get("effort", "")

        p_color, p_label = PRIORITY_COLORS.get(priority, (MID_GRAY, priority.upper()))

        badge = Table(
            [[Paragraph(p_label, ParagraphStyle(
                "priority_badge", fontSize=7, textColor=white,
                fontName="Helvetica-Bold", alignment=TA_CENTER,
            ))]],
            colWidths=[0.55 * inch],
            rowHeights=[14],
        )
        badge.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), p_color),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))

        content_w = PAGE_W - 2.2 * cm - 0.65 * inch
        content_rows = []
        if recommendation:
            content_rows.append([Paragraph(f"<b>{recommendation}</b>", styles["body"])])
        if rationale:
            content_rows.append([Paragraph(rationale, styles["body_small"])])
        if effort:
            content_rows.append([Paragraph(f"Effort: {effort.title()}", styles["label"])])

        content_table = Table(content_rows, colWidths=[content_w])
        content_table.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))

        rec_table = Table(
            [[badge, content_table]],
            colWidths=[0.65 * inch, content_w],
        )
        rec_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, HexColor("#DDDDDD")),
            ("LINEBEFORE", (0, 0), (0, -1), 4, p_color),
        ]))
        elements.append(rec_table)
        elements.append(Spacer(1, 8))

    elements.append(PageBreak())
    return elements


# ─── Appendix ────────────────────────────────────────────────────────────────
def build_appendix(analysis: dict, styles: dict) -> list:
    elements = section_header("Appendix — Methodology &amp; Disclaimer", styles)

    analyzed_at = analysis.get("analyzed_at", "")
    if analyzed_at:
        try:
            dt = datetime.fromisoformat(analyzed_at.replace("Z", "+00:00"))
            analyzed_at = dt.strftime("%B %d, %Y at %H:%M UTC")
        except Exception:
            pass

    methodology = (
        "<b>Data Collection:</b> Competitor discovery was performed using DuckDuckGo search based on "
        "industry-specific queries. Competitor websites were scraped using publicly accessible HTTP requests. "
        "Review data was sourced from Trustpilot and web search results.<br/><br/>"
        "<b>AI Analysis:</b> Competitive insights were generated using Claude (Anthropic) based on "
        "the collected data. The AI was instructed to cite specific evidence rather than speculate, "
        "and to flag gaps where data was sparse or unavailable.<br/><br/>"
        f"<b>Report Generated:</b> {analyzed_at}<br/><br/>"
        "<b>Disclaimer:</b> This report is based entirely on publicly available information. "
        "Pricing, services, and other details may have changed since data was collected. "
        "This report is intended for internal strategic planning purposes only and should not "
        "be shared externally. Xpatz Global should verify key findings before making major "
        "business decisions based on this data."
    )

    elements.append(Paragraph(methodology, styles["body"]))
    return elements


# ─── Main PDF Generation ──────────────────────────────────────────────────────
def generate_pdf(
    analysis_path: str = ".tmp/analysis.json",
    business_profile_path: str = "config/business_profile.json",
    logo_path: str = "assets/xpatz_logo.png",
    output_path: str = None,
) -> str:
    # Load data
    with open(analysis_path, "r") as f:
        analysis = json.load(f)

    with open(business_profile_path, "r") as f:
        profile = json.load(f)

    company_name = profile["company"]["name"]
    n_competitors = analysis.get("competitors_analyzed", 0)
    report_date = datetime.now().strftime("%B %d, %Y")

    # Output path
    if output_path is None:
        date_slug = datetime.now().strftime("%Y-%m-%d")
        output_path = f"competitor_analysis_{date_slug}.pdf"

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    # Check logo
    if logo_path and not os.path.exists(logo_path):
        print(f"[warn] Logo not found at {logo_path} — generating PDF without logo")
        logo_path = None

    styles = build_styles()

    # Document setup
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.1 * cm,
        rightMargin=1.1 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.4 * cm,
        title=f"Competitor Intelligence Report — {company_name}",
        author=company_name,
        subject="Competitive Analysis",
    )

    footer_cb = make_footer_callback(logo_path, report_date, company_name)
    elements = []

    # Build sections
    elements += build_cover(logo_path, company_name, report_date, n_competitors, styles)
    elements += build_executive_summary(analysis, styles)
    elements += build_competitor_profiles(analysis, styles)
    elements += build_positioning_matrix(analysis, styles)
    elements += build_doing_well(analysis, styles)
    elements += build_gaps(analysis, styles)
    elements += build_recommendations(analysis, styles)
    elements += build_appendix(analysis, styles)

    doc.build(elements, onFirstPage=footer_cb, onLaterPages=footer_cb)

    print(f"[done] PDF generated → {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate branded PDF competitor report")
    parser.add_argument("--analysis", default=".tmp/analysis.json")
    parser.add_argument("--profile", default="config/business_profile.json")
    parser.add_argument("--logo", default="assets/xpatz_logo.png")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    path = generate_pdf(
        analysis_path=args.analysis,
        business_profile_path=args.profile,
        logo_path=args.logo,
        output_path=args.output,
    )
    print(f"Report saved to: {path}")
