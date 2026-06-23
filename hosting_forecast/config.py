"""
Central configuration for the Hosting forecasting & variance automation.

Anchors reflect a typical mid-size hosting business: roughly 2.8M customers,
~5% monthly churn, ~$15/month ARPC.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict

# ── Paths ──────────────────────────────────────────────────────────────
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(PKG_DIR, "sample_data")
SAMPLE_ACTUALS = os.path.join(SAMPLE_DIR, "hosting_actuals.csv")
OUTPUT_DIR = os.path.join(PKG_DIR, "output")
DEFAULT_PDF = os.path.join(OUTPUT_DIR, "hosting_variance_summary.pdf")

# ── Canonical schema ───────────────────────────────────────────────────
# One row per month. The first four driver columns roll forward; revenue is
# derived. Budget_* columns are the plan the actuals are measured against.
REQUIRED_COLUMNS = [
    "month",                # YYYY-MM-01 (first of month)
    "opening_customers",
    "new_customers",
    "churned_customers",
    "closing_customers",
    "arpc",                 # average revenue per customer, monthly $
    "revenue",              # avg_customers * arpc
]
BUDGET_COLUMNS = ["budget_revenue", "budget_customers", "budget_arpc"]


# ── Driver baseline (Hosting segment) ──────────────────────────────────
@dataclass
class HostingBaseline:
    """Starting point and base-case driver assumptions for a forecast."""

    opening_customers: float = 2_800_000.0   # ~2.8M Hosting customers
    new_customers: float = 165_000.0         # gross monthly adds
    churn_rate: float = 0.05                  # 5% monthly logo churn
    arpc: float = 15.00                       # $/customer/month
    arpc_growth_m: float = 0.004              # ~0.4%/mo upsell/price (≈5%/yr)
    new_growth_m: float = 0.003               # gross-add momentum per month


# ── Scenarios ──────────────────────────────────────────────────────────
# Deltas applied on top of the base case for the bear/base/bull views. Values
# are absolute adjustments to monthly churn and multiplicative factors on adds /
# ARPC growth.
@dataclass
class Scenario:
    name: str
    churn_delta: float       # added to monthly churn_rate
    new_factor: float        # multiplies gross monthly adds
    arpc_growth_factor: float  # multiplies monthly ARPC growth


SCENARIOS: Dict[str, Scenario] = {
    "bear": Scenario("Bear", churn_delta=+0.010, new_factor=0.85, arpc_growth_factor=0.5),
    "base": Scenario("Base", churn_delta=0.000, new_factor=1.00, arpc_growth_factor=1.0),
    "bull": Scenario("Bull", churn_delta=-0.008, new_factor=1.15, arpc_growth_factor=1.6),
}

# Top-down sanity-check target: management YoY revenue growth guidance and the
# tolerance band within which bottom-up and top-down should agree.
TOPDOWN_YOY_GROWTH = 0.10     # 10% YoY guidance
TOPDOWN_TOLERANCE = 0.02      # agree within 2%

# ── Branding ───────────────────────────────────────────────────────────
NAVY = "#1B3A6B"
TEAL = "#00A4A6"
FAV = "#1F6B2E"      # favourable variance (green)
UNF = "#B11226"      # unfavourable variance (red)
LGREY = "#F3F4F6"
MGREY = "#E5E7EB"


def ensure_dirs() -> None:
    """Create sample_data and output directories if missing."""
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
