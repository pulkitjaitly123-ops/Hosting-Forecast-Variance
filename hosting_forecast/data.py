"""
Data layer: synthetic Hosting actuals generator + CSV/Excel loader.

The generator produces a realistic monthly history (customer roll-forward with
seasonality and light noise) plus a budget plan, so the tool runs instantly for
a demo. The loader reads and validates a real monthly file with the same schema,
so the same code path serves a live reforecast.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


# ── Synthetic actuals ──────────────────────────────────────────────────
def generate_sample_actuals(
    months: int = 36,
    start: str = "2023-01-01",
    seed: int = 42,
    write: bool = True,
) -> pd.DataFrame:
    """
    Build `months` of monthly Hosting actuals plus a budget plan.

    Actuals are the base-case driver roll-forward perturbed by:
      * seasonality  — a Q1 renewal bump in gross adds (Jan-Mar)
      * noise         — small random shocks to adds, churn and ARPC
    The budget is the clean base-case plan with no noise, representing the
    annual plan the actuals are measured against.
    """
    rng = np.random.default_rng(seed)
    base = config.HostingBaseline()
    dates = pd.date_range(start=start, periods=months, freq="MS")

    # Seasonal multiplier on gross adds: stronger in Q1 (domain renewal halo).
    season = {1: 1.18, 2: 1.10, 3: 1.06, 11: 1.08, 12: 1.05}

    act_rows, bud_rows = [], []
    a_open = base.opening_customers
    b_open = base.opening_customers
    a_new = base.new_customers
    b_new = base.new_customers
    a_arpc = base.arpc
    b_arpc = base.arpc

    for d in dates:
        s = season.get(d.month, 1.0)

        # ---- Budget (clean base-case plan) ----
        b_churned = b_open * base.churn_rate
        b_close = b_open + b_new - b_churned
        b_avg = (b_open + b_close) / 2.0
        b_rev = b_avg * b_arpc
        bud_rows.append(dict(month=d, customers=b_close, arpc=b_arpc, revenue=b_rev))

        # ---- Actuals (seasonal + noisy) ----
        new_act = a_new * s * (1 + rng.normal(0, 0.03))
        churn_act = base.churn_rate * (1 + rng.normal(0, 0.06))
        arpc_act = a_arpc * (1 + rng.normal(0, 0.006))
        churned = a_open * churn_act
        close = a_open + new_act - churned
        avg = (a_open + close) / 2.0
        rev = avg * arpc_act

        act_rows.append(
            dict(
                month=d,
                opening_customers=a_open,
                new_customers=new_act,
                churned_customers=churned,
                closing_customers=close,
                arpc=arpc_act,
                revenue=rev,
            )
        )

        # roll forward
        a_open = close
        b_open = b_close
        a_new *= 1 + base.new_growth_m
        b_new *= 1 + base.new_growth_m
        a_arpc *= 1 + base.arpc_growth_m
        b_arpc *= 1 + base.arpc_growth_m

    act = pd.DataFrame(act_rows)
    bud = pd.DataFrame(bud_rows)
    act["budget_customers"] = bud["customers"].values
    act["budget_arpc"] = bud["arpc"].values
    act["budget_revenue"] = bud["revenue"].values

    # Tidy types: integer-ish customer counts, rounded dollars.
    for c in ["opening_customers", "new_customers", "churned_customers",
              "closing_customers", "budget_customers"]:
        act[c] = act[c].round(0)
    for c in ["arpc", "budget_arpc"]:
        act[c] = act[c].round(2)
    for c in ["revenue", "budget_revenue"]:
        act[c] = act[c].round(0)
    act["month"] = act["month"].dt.strftime("%Y-%m-01")

    if write:
        config.ensure_dirs()
        act.to_csv(config.SAMPLE_ACTUALS, index=False)
    return act


# ── Loader / validation ────────────────────────────────────────────────
def load_actuals(path: str | None = None) -> pd.DataFrame:
    """
    Load a monthly Hosting actuals file (CSV or Excel) and validate its schema.

    If `path` is None and no sample exists yet, one is generated. Missing budget
    columns are tolerated (variance-vs-budget is then skipped downstream).
    """
    if path is None:
        path = config.SAMPLE_ACTUALS
        import os
        if not os.path.exists(path):
            generate_sample_actuals()

    if str(path).lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    missing = [c for c in config.REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Input file is missing required columns: {missing}. "
            f"Expected schema: {config.REQUIRED_COLUMNS}"
        )

    df["month"] = pd.to_datetime(df["month"])
    df = df.sort_values("month").reset_index(drop=True)

    num_cols = [c for c in config.REQUIRED_COLUMNS if c != "month"]
    num_cols += [c for c in config.BUDGET_COLUMNS if c in df.columns]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df[num_cols].isna().any().any():
        bad = df[num_cols].isna().any()
        raise ValueError(f"Non-numeric / blank values found in: {list(bad[bad].index)}")

    return df


def has_budget(df: pd.DataFrame) -> bool:
    """True when the frame carries a full budget plan."""
    return all(c in df.columns for c in config.BUDGET_COLUMNS)


if __name__ == "__main__":
    frame = generate_sample_actuals()
    print(f"Generated {len(frame)} months -> {config.SAMPLE_ACTUALS}\n")
    with pd.option_context("display.max_columns", None, "display.width", 160):
        print(frame.head(6).to_string(index=False))
    last = frame.iloc[-1]
    print(
        f"\nLatest month {last['month']}: "
        f"customers={last['closing_customers']:,.0f}, "
        f"ARPC=${last['arpc']:.2f}, revenue=${last['revenue']:,.0f}"
    )
