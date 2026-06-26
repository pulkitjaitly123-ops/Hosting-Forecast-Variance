"""
Bottom-up, driver-based revenue forecast for a subscription revenue line.

The roll-forward is a simple, auditable monthly progression:

    churned       = opening_customers * churn_rate
    closing       = opening + new - churned
    avg_customers = (opening + closing) / 2
    revenue       = avg_customers * arpc

Forecasts run under bear / base / bull scenarios and are sanity-checked against
a top-down YoY growth target so the two approaches can be shown to agree within
tolerance — the hallmark of a defensible forecast.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

import numpy as np
import pandas as pd

from . import config
from .config import HostingBaseline, Scenario, SCENARIOS


@dataclass
class DriverOverrides:
    """Optional UI/CLI overrides applied to the base case before forecasting."""

    churn_rate: Optional[float] = None
    arpc_growth_m: Optional[float] = None
    new_customers: Optional[float] = None
    new_growth_m: Optional[float] = None


def _apply(base: HostingBaseline, ov: Optional[DriverOverrides]) -> HostingBaseline:
    if ov is None:
        return base
    kw = {k: v for k, v in vars(ov).items() if v is not None}
    return replace(base, **kw)


def starting_point(history: Optional[pd.DataFrame]) -> HostingBaseline:
    """
    Derive forecast starting drivers from the tail of an actuals history.

    Opening customers = last closing balance; ARPC and gross-add level seed from
    the most recent actuals. Falls back to the static baseline when no history.
    """
    base = HostingBaseline()
    if history is None or len(history) == 0:
        return base
    last = history.iloc[-1]
    recent = history.tail(3)
    implied_churn = float((recent["churned_customers"] / recent["opening_customers"]).mean())
    return replace(
        base,
        opening_customers=float(last["closing_customers"]),
        new_customers=float(recent["new_customers"].mean()),
        arpc=float(last["arpc"]),
        churn_rate=implied_churn,
    )


def forecast_scenario(
    base: HostingBaseline,
    months: int,
    scenario: Scenario,
    start_month: pd.Timestamp,
) -> pd.DataFrame:
    """Roll the driver model forward `months` periods under one scenario."""
    churn = base.churn_rate + scenario.churn_delta
    new = base.new_customers * scenario.new_factor
    arpc = base.arpc
    arpc_growth = base.arpc_growth_m * scenario.arpc_growth_factor
    opening = base.opening_customers

    dates = pd.date_range(start=start_month, periods=months, freq="MS")
    rows = []
    for d in dates:
        churned = opening * churn
        closing = opening + new - churned
        avg = (opening + closing) / 2.0
        rev = avg * arpc
        rows.append(
            dict(
                month=d,
                scenario=scenario.name,
                opening_customers=opening,
                new_customers=new,
                churned_customers=churned,
                closing_customers=closing,
                avg_customers=avg,
                arpc=arpc,
                revenue=rev,
            )
        )
        opening = closing
        new *= 1 + base.new_growth_m
        arpc *= 1 + arpc_growth
    return pd.DataFrame(rows)


def forecast_all(
    history: Optional[pd.DataFrame] = None,
    months: int = 12,
    overrides: Optional[DriverOverrides] = None,
    start_month: Optional[pd.Timestamp] = None,
) -> Dict[str, pd.DataFrame]:
    """Produce bear/base/bull forecasts as a dict of DataFrames."""
    base = _apply(starting_point(history), overrides)
    if start_month is None:
        if history is not None and len(history):
            start_month = history["month"].max() + pd.offsets.MonthBegin(1)
        else:
            start_month = pd.Timestamp.today().normalize().replace(day=1)
    return {
        key: forecast_scenario(base, months, sc, start_month)
        for key, sc in SCENARIOS.items()
    }


def topdown_check(
    history: pd.DataFrame,
    base_forecast: pd.DataFrame,
    yoy_growth: float = config.TOPDOWN_YOY_GROWTH,
    tolerance: float = config.TOPDOWN_TOLERANCE,
) -> dict:
    """
    Compare the bottom-up forecast total to a top-down YoY growth target.

    Top-down: take trailing-12-month actual revenue, grow by `yoy_growth`.
    Bottom-up: sum the next-12-month base-case forecast revenue.
    Return both, the gap, and whether they agree within tolerance.
    """
    n = min(12, len(history), len(base_forecast))
    ttm_actual = float(history["revenue"].tail(n).sum())
    topdown = ttm_actual * (1 + yoy_growth)
    bottomup = float(base_forecast["revenue"].head(n).sum())
    gap = (bottomup - topdown) / topdown if topdown else float("nan")
    return {
        "ttm_actual": ttm_actual,
        "topdown_target": topdown,
        "bottomup_total": bottomup,
        "gap_pct": gap,
        "agree": abs(gap) <= tolerance,
        "tolerance": tolerance,
        "yoy_growth": yoy_growth,
    }


if __name__ == "__main__":
    from .data import load_actuals

    hist = load_actuals()
    fcs = forecast_all(hist, months=12)
    base = fcs["base"]

    print("Bottom-up revenue forecast, base case (next 12 months)\n")
    show = base[["month", "closing_customers", "arpc", "revenue"]].copy()
    show["month"] = show["month"].dt.strftime("%Y-%m")
    print(show.to_string(index=False,
          formatters={"closing_customers": "{:,.0f}".format,
                      "arpc": "${:.2f}".format,
                      "revenue": "${:,.0f}".format}))

    chk = topdown_check(hist, base)
    print("\nTop-down vs bottom-up sanity check")
    print(f"  TTM actual revenue : ${chk['ttm_actual']:,.0f}")
    print(f"  Top-down target    : ${chk['topdown_target']:,.0f}  "
          f"(+{chk['yoy_growth']:.0%} YoY)")
    print(f"  Bottom-up forecast : ${chk['bottomup_total']:,.0f}")
    print(f"  Gap                : {chk['gap_pct']:+.2%}  "
          f"-> {'AGREE' if chk['agree'] else 'REVIEW'} "
          f"(tol +/-{chk['tolerance']:.0%})")

    print("\nScenario 12M revenue totals")
    for k, df in fcs.items():
        print(f"  {df['scenario'].iloc[0]:<5}: ${df['revenue'].sum():,.0f}")
