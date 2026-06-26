"""
Variance analysis: actual vs plan, with a volume/rate (price) bridge.

The centrepiece is the revenue-variance decomposition. Total revenue variance is
split into the part caused by selling to more/fewer customers (volume) and the
part caused by a higher/lower price per customer (rate), plus a small joint term:

    revenue   = customers * arpc
    Δrevenue  = (Δcustomers * arpc_plan)        # volume effect
              + (Δarpc * customers_plan)        # rate effect
              + (Δcustomers * Δarpc)            # joint / residual

Favourable means actual revenue came in above plan. Forecast accuracy is
reported as MAPE and bias over the overlap window.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _avg_customers(df: pd.DataFrame, prefix: str = "") -> pd.Series:
    """Average customers for a row; prefer opening/closing, else the count col."""
    o, c = f"{prefix}opening_customers", f"{prefix}closing_customers"
    if o in df and c in df:
        return (df[o] + df[c]) / 2.0
    return df[f"{prefix}customers" if f"{prefix}customers" in df else f"{prefix}closing_customers"]


def variance_table(actual: pd.DataFrame) -> pd.DataFrame:
    """
    Per-month actual-vs-budget variance table.

    Requires the budget_* columns; returns one row per month with $ and %
    variance plus a favourable/unfavourable flag.
    """
    if not all(c in actual for c in config.BUDGET_COLUMNS):
        raise ValueError("Budget columns required for variance_table.")

    out = pd.DataFrame({"month": actual["month"]})
    out["actual_revenue"] = actual["revenue"]
    out["budget_revenue"] = actual["budget_revenue"]
    out["var_usd"] = out["actual_revenue"] - out["budget_revenue"]
    out["var_pct"] = out["var_usd"] / out["budget_revenue"]
    out["status"] = np.where(out["var_usd"] >= 0, "Favourable", "Unfavourable")
    out["actual_customers"] = _avg_customers(actual)
    out["budget_customers"] = actual["budget_customers"]
    out["actual_arpc"] = actual["arpc"]
    out["budget_arpc"] = actual["budget_arpc"]
    return out


def volume_rate_bridge(actual: pd.DataFrame, period: str = "ttm") -> dict:
    """
    Decompose the revenue variance for a window into volume vs rate effects.

    period: "ttm" (trailing 12), "ytd" (latest calendar year), or "all".
    Uses average customers and ARPC so the three effects reconcile exactly to
    the total revenue variance.
    """
    if not all(c in actual for c in config.BUDGET_COLUMNS):
        raise ValueError("Budget columns required for volume_rate_bridge.")

    df = actual.copy()
    if period == "ttm":
        df = df.tail(12)
    elif period == "ytd":
        last_year = df["month"].max().year
        df = df[df["month"].dt.year == last_year]

    act_cust = _avg_customers(df)
    bud_cust = df["budget_customers"]
    act_arpc = df["arpc"]
    bud_arpc = df["budget_arpc"]

    act_rev = float((act_cust * act_arpc).sum())
    bud_rev = float((bud_cust * bud_arpc).sum())

    d_cust = act_cust - bud_cust
    d_arpc = act_arpc - bud_arpc
    volume = float((d_cust * bud_arpc).sum())
    rate = float((d_arpc * bud_cust).sum())
    joint = float((d_cust * d_arpc).sum())
    total = act_rev - bud_rev

    return {
        "period": period,
        "n_months": int(len(df)),
        "actual_revenue": act_rev,
        "budget_revenue": bud_rev,
        "total_variance": total,
        "total_variance_pct": total / bud_rev if bud_rev else float("nan"),
        "volume_effect": volume,
        "rate_effect": rate,
        "joint_effect": joint,
        "status": "Favourable" if total >= 0 else "Unfavourable",
        # residual proves the bridge reconciles (should be ~0)
        "reconciliation_residual": total - (volume + rate + joint),
    }


def accuracy_metrics(actual: pd.DataFrame) -> dict:
    """MAPE and bias of actual revenue vs the budget plan over all months."""
    if "budget_revenue" not in actual:
        raise ValueError("Budget revenue required for accuracy_metrics.")
    a = actual["revenue"].to_numpy(dtype=float)
    b = actual["budget_revenue"].to_numpy(dtype=float)
    ape = np.abs(a - b) / np.where(b == 0, np.nan, b)
    return {
        "mape": float(np.nanmean(ape)),
        "bias": float(np.mean(a - b)),
        "bias_pct": float(np.sum(a - b) / np.sum(b)) if np.sum(b) else float("nan"),
        "n_months": int(len(actual)),
    }


def narrative(bridge: dict, acc: dict) -> list[str]:
    """Plain-English bullets summarising the variance story (no em dashes)."""
    def m(x: float) -> str:
        return f"${abs(x) / 1e6:,.1f}M"

    bullets = []
    dirn = "above" if bridge["total_variance"] >= 0 else "below"
    bullets.append(
        f"Revenue came in {m(bridge['actual_revenue'])} over the trailing "
        f"{bridge['n_months']} months, {m(bridge['total_variance'])} "
        f"({bridge['total_variance_pct']:+.1%}) {dirn} plan ({bridge['status'].lower()})."
    )
    vol_dir = "added" if bridge["volume_effect"] >= 0 else "cost"
    bullets.append(
        f"Volume {vol_dir} {m(bridge['volume_effect'])}: customer count ran "
        f"{'ahead of' if bridge['volume_effect'] >= 0 else 'behind'} plan, the "
        f"larger driver of the gap."
        if abs(bridge["volume_effect"]) >= abs(bridge["rate_effect"]) else
        f"Volume {vol_dir} {m(bridge['volume_effect'])} from the plan customer base."
    )
    rate_dir = "added" if bridge["rate_effect"] >= 0 else "cost"
    bullets.append(
        f"Rate (ARPC) {rate_dir} {m(bridge['rate_effect'])}: realised price per "
        f"customer was {'above' if bridge['rate_effect'] >= 0 else 'below'} plan."
    )
    bullets.append(
        f"Forecast accuracy: MAPE {acc['mape']:.1%}, bias {acc['bias_pct']:+.1%} "
        f"({'optimistic plan' if acc['bias_pct'] >= 0 else 'conservative plan'})."
    )
    return bullets


if __name__ == "__main__":
    from .data import load_actuals

    act = load_actuals()
    vt = variance_table(act)
    print("Actual vs Budget — last 6 months\n")
    show = vt.tail(6).copy()
    show["month"] = show["month"].dt.strftime("%Y-%m")
    print(show[["month", "actual_revenue", "budget_revenue", "var_usd", "var_pct", "status"]]
          .to_string(index=False,
                     formatters={"actual_revenue": "${:,.0f}".format,
                                 "budget_revenue": "${:,.0f}".format,
                                 "var_usd": "${:,.0f}".format,
                                 "var_pct": "{:+.1%}".format}))

    br = volume_rate_bridge(act, period="ttm")
    print(f"\nVolume / Rate bridge — trailing {br['n_months']} months")
    print(f"  Budget revenue       : ${br['budget_revenue']:,.0f}")
    print(f"  + Volume effect      : ${br['volume_effect']:+,.0f}")
    print(f"  + Rate (ARPC) effect : ${br['rate_effect']:+,.0f}")
    print(f"  + Joint effect       : ${br['joint_effect']:+,.0f}")
    print(f"  = Actual revenue     : ${br['actual_revenue']:,.0f}")
    print(f"  Total variance       : ${br['total_variance']:+,.0f} "
          f"({br['total_variance_pct']:+.1%}, {br['status']})")
    print(f"  Reconciliation resid : ${br['reconciliation_residual']:,.4f} (should be ~0)")

    acc = accuracy_metrics(act)
    print(f"\nAccuracy: MAPE {acc['mape']:.2%}, bias {acc['bias_pct']:+.2%} "
          f"over {acc['n_months']} months")

    print("\nNarrative")
    for b in narrative(br, acc):
        print(f"  - {b}")
