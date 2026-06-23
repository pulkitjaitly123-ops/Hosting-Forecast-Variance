"""
One-page executive variance summary (PDF) via reportlab.

Layout: title band, KPI strip, volume/rate bridge table, forecast outlook, and
auto-generated narrative bullets. Palette matches build_model.py (navy / teal,
green favourable / red unfavourable).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Flowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from . import config
from . import variance as V
from . import forecast as Fc

NAVY = colors.HexColor(config.NAVY)
TEAL = colors.HexColor(config.TEAL)
FAV = colors.HexColor(config.FAV)
UNF = colors.HexColor(config.UNF)
LGREY = colors.HexColor(config.LGREY)
MGREY = colors.HexColor(config.MGREY)


def _m(x: float) -> str:
    return f"${x / 1e6:,.1f}M"


def _signed_m(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}${abs(x) / 1e6:,.1f}M"


class _Band(Flowable):
    """A coloured title band spanning the frame width."""

    def __init__(self, title: str, subtitle: str, width: float, height: float = 0.62 * inch):
        super().__init__()
        self.title, self.subtitle = title, subtitle
        self.width, self.height = width, height

    def draw(self):
        c = self.canv
        c.setFillColor(NAVY)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        c.setFillColor(TEAL)
        c.rect(0, 0, 0.10 * inch, self.height, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(0.28 * inch, self.height - 0.30 * inch, self.title)
        c.setFont("Helvetica", 9)
        c.drawString(0.28 * inch, self.height - 0.50 * inch, self.subtitle)


def _kpi_strip(kpis, width):
    """Row of KPI cells: (label, value, delta_text, favourable?)."""
    cells, styles = [], []
    body, deltas = [], []
    for label, value, delta, fav in kpis:
        body.append(Paragraph(
            f'<font size=8 color="#5b6470">{label}</font><br/>'
            f'<font size=15 color="#1B3A6B"><b>{value}</b></font>', _PS["kpi"]))
        col = config.FAV if fav else config.UNF
        deltas.append(Paragraph(f'<font size=8 color="{col}">{delta}</font>', _PS["kpi"]))
    t = Table([body, deltas], colWidths=[width / len(kpis)] * len(kpis))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LGREY),
        ("BOX", (0, 0), (-1, -1), 0.5, MGREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


_PS = None


def _init_styles():
    global _PS
    if _PS:
        return
    ss = getSampleStyleSheet()
    _PS = {
        "kpi": ParagraphStyle("kpi", parent=ss["Normal"], leading=13),
        "sec": ParagraphStyle("sec", parent=ss["Normal"], fontName="Helvetica-Bold",
                              fontSize=11, textColor=NAVY, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5, leading=14),
        "bullet": ParagraphStyle("bullet", parent=ss["Normal"], fontSize=9.5,
                                 leading=14, leftIndent=10, bulletIndent=0),
        "foot": ParagraphStyle("foot", parent=ss["Normal"], fontSize=7.5,
                              textColor=colors.HexColor("#888888")),
    }


def build_report(
    actual: pd.DataFrame,
    out_path: Optional[str] = None,
    scenario_totals: Optional[dict] = None,
    topdown: Optional[dict] = None,
) -> str:
    """Render the one-page PDF and return its path."""
    _init_styles()
    config.ensure_dirs()
    out_path = out_path or config.DEFAULT_PDF

    bridge = V.volume_rate_bridge(actual, period="ttm")
    acc = V.accuracy_metrics(actual)
    bullets = V.narrative(bridge, acc)
    last = actual.iloc[-1]
    avg_cust_last = (last["opening_customers"] + last["closing_customers"]) / 2.0
    implied_churn = last["churned_customers"] / last["opening_customers"]

    doc = SimpleDocTemplate(
        out_path, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    W = doc.width
    story = []

    period_lbl = f"{actual['month'].min():%b %Y} to {actual['month'].max():%b %Y}"
    story.append(_Band("GoDaddy Hosting — Revenue Variance Summary",
                       f"Trailing 12 months ending {actual['month'].max():%B %Y}   |   "
                       f"History: {period_lbl}", W))
    story.append(Spacer(1, 10))

    # KPI strip
    kpis = [
        ("TTM Revenue", _m(bridge["actual_revenue"]),
         f"{bridge['total_variance_pct']:+.1%} vs plan", bridge["total_variance"] >= 0),
        ("Variance $", _signed_m(bridge["total_variance"]),
         bridge["status"], bridge["total_variance"] >= 0),
        ("Customers", f"{avg_cust_last / 1e6:,.2f}M",
         f"{(avg_cust_last - last['budget_customers']) / last['budget_customers']:+.1%} vs plan",
         avg_cust_last >= last["budget_customers"]),
        ("ARPC / mo", f"${last['arpc']:,.2f}",
         f"{(last['arpc'] - last['budget_arpc']) / last['budget_arpc']:+.1%} vs plan",
         last["arpc"] >= last["budget_arpc"]),
        ("Churn / mo", f"{implied_churn:.1%}", f"MAPE {acc['mape']:.1%}", implied_churn <= 0.055),
    ]
    story.append(_kpi_strip(kpis, W))

    # Volume / rate bridge table
    story.append(Paragraph("Revenue Variance Bridge — Volume vs Rate", _PS["sec"]))
    bridge_rows = [
        ["Component", "Amount", "Driver"],
        ["Budget revenue (plan)", _m(bridge["budget_revenue"]), "Annual plan baseline"],
        ["Volume effect", _signed_m(bridge["volume_effect"]),
         "Δ customers × plan ARPC"],
        ["Rate effect (ARPC)", _signed_m(bridge["rate_effect"]),
         "Δ ARPC × plan customers"],
        ["Joint / mix", _signed_m(bridge["joint_effect"]), "Δ customers × Δ ARPC"],
        ["Actual revenue", _m(bridge["actual_revenue"]),
         f"Total variance {_signed_m(bridge['total_variance'])} "
         f"({bridge['total_variance_pct']:+.1%})"],
    ]
    bt = Table(bridge_rows, colWidths=[1.9 * inch, 1.3 * inch, W - 3.2 * inch])
    fav = bridge["total_variance"] >= 0
    bt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 1), (-1, 1), LGREY),
        ("BACKGROUND", (0, -1), (-1, -1), FAV if fav else UNF),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 2), (1, 2), FAV if bridge["volume_effect"] >= 0 else UNF),
        ("TEXTCOLOR", (1, 3), (1, 3), FAV if bridge["rate_effect"] >= 0 else UNF),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, MGREY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(bt)

    # Forecast outlook
    if scenario_totals or topdown:
        story.append(Paragraph("Forward Outlook — Next 12 Months", _PS["sec"]))
        out_rows = [["Scenario", "Forecast revenue", "Note"]]
        if scenario_totals:
            for key in ("bear", "base", "bull"):
                if key in scenario_totals:
                    out_rows.append([key.capitalize(), _m(scenario_totals[key]),
                                     "Bottom-up driver model"])
        if topdown:
            out_rows.append(["Top-down target", _m(topdown["topdown_target"]),
                             f"+{topdown['yoy_growth']:.0%} YoY; bottom-up gap "
                             f"{topdown['gap_pct']:+.1%} "
                             f"({'agrees' if topdown['agree'] else 'review'})"])
        ot = Table(out_rows, colWidths=[1.6 * inch, 1.6 * inch, W - 3.2 * inch])
        ot.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, MGREY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LGREY]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(ot)

    # Narrative
    story.append(Paragraph("Key Takeaways", _PS["sec"]))
    for b in bullets:
        story.append(Paragraph(b, _PS["bullet"], bulletText="•"))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Generated {date.today():%d %b %Y} by hosting_forecast. Driver model: "
        f"revenue = average customers × ARPC. Favourable = actual above plan.",
        _PS["foot"]))

    doc.build(story)
    return out_path


def build_default(out_path: Optional[str] = None) -> str:
    """Convenience: load sample actuals, run forecast, render the PDF."""
    from .data import load_actuals
    act = load_actuals()
    fcs = Fc.forecast_all(act, months=12)
    totals = {k: float(df["revenue"].sum()) for k, df in fcs.items()}
    td = Fc.topdown_check(act, fcs["base"])
    return build_report(act, out_path, scenario_totals=totals, topdown=td)


if __name__ == "__main__":
    path = build_default()
    import os
    print(f"Wrote PDF -> {path} ({os.path.getsize(path):,} bytes)")
