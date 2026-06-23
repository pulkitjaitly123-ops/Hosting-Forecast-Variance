"""
Streamlit dashboard — Hosting revenue forecasting & variance.

Run:
    streamlit run hosting_forecast/app.py

Sidebar lets you use the bundled sample or upload a monthly actuals file, pick a
scenario and forecast horizon, and tune the key drivers. The main panel shows
forecast-vs-actual, the customer roll-forward, the volume/rate variance bridge,
the driver decomposition, and a one-click PDF export.

This module is import-safe: it only renders when run under Streamlit, so the
package can still be imported (and unit-run) without a Streamlit context.
"""
from __future__ import annotations

import io

import pandas as pd

# Allow `python -m hosting_forecast.app` and `streamlit run .../app.py` alike.
try:
    from . import config, data, forecast as Fc, variance as V, pdf_report
except ImportError:  # run as a top-level script by streamlit
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from hosting_forecast import config, data, forecast as Fc, variance as V, pdf_report


def _esc(text: str) -> str:
    """Escape $ so Streamlit markdown does not treat it as LaTeX math."""
    return text.replace("$", "\\$")


def _fig_forecast_vs_actual(actual, fcs):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=actual["month"], y=actual["revenue"], name="Actual",
        mode="lines", line=dict(color=config.NAVY, width=3)))
    if "budget_revenue" in actual:
        fig.add_trace(go.Scatter(
            x=actual["month"], y=actual["budget_revenue"], name="Budget",
            mode="lines", line=dict(color="#9aa4b2", width=2, dash="dot")))
    colors = {"bear": config.UNF, "base": config.TEAL, "bull": config.FAV}
    for key, df in fcs.items():
        fig.add_trace(go.Scatter(
            x=df["month"], y=df["revenue"], name=f"Forecast ({key})",
            mode="lines", line=dict(color=colors[key], width=2,
                                    dash="solid" if key == "base" else "dash")))
    fig.update_layout(
        title="Revenue: actual, budget, and forecast scenarios",
        yaxis_title="Monthly revenue ($)", height=380,
        margin=dict(t=46, b=10, l=10, r=10), legend=dict(orientation="h", y=-0.2))
    return fig


def _fig_rollforward(actual):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Bar(x=actual["month"], y=actual["new_customers"],
                         name="New", marker_color=config.TEAL))
    fig.add_trace(go.Bar(x=actual["month"], y=-actual["churned_customers"],
                         name="Churned", marker_color=config.UNF))
    fig.add_trace(go.Scatter(x=actual["month"], y=actual["closing_customers"],
                             name="Closing customers", mode="lines",
                             line=dict(color=config.NAVY, width=3), yaxis="y2"))
    fig.update_layout(
        title="Customer roll-forward (adds vs churn) and balance",
        barmode="relative", height=360, margin=dict(t=46, b=10, l=10, r=10),
        yaxis=dict(title="Monthly flow"),
        yaxis2=dict(title="Closing balance", overlaying="y", side="right",
                    showgrid=False),
        legend=dict(orientation="h", y=-0.2))
    return fig


def _fig_bridge(bridge):
    import plotly.graph_objects as go
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "total"],
        x=["Budget", "Volume", "Rate (ARPC)", "Joint", "Actual"],
        y=[bridge["budget_revenue"], bridge["volume_effect"],
           bridge["rate_effect"], bridge["joint_effect"], 0],
        text=[f"${bridge['budget_revenue']/1e6:,.1f}M",
              f"{'+' if bridge['volume_effect']>=0 else '-'}${abs(bridge['volume_effect'])/1e6:,.1f}M",
              f"{'+' if bridge['rate_effect']>=0 else '-'}${abs(bridge['rate_effect'])/1e6:,.1f}M",
              f"{'+' if bridge['joint_effect']>=0 else '-'}${abs(bridge['joint_effect'])/1e6:,.1f}M",
              f"${bridge['actual_revenue']/1e6:,.1f}M"],
        textposition="outside",
        connector=dict(line=dict(color="#9aa4b2")),
        increasing=dict(marker=dict(color=config.FAV)),
        decreasing=dict(marker=dict(color=config.UNF)),
        totals=dict(marker=dict(color=config.NAVY))))
    fig.update_layout(
        title=f"Revenue variance bridge — trailing {bridge['n_months']} months",
        height=380, margin=dict(t=46, b=10, l=10, r=10), yaxis_title="$")
    return fig


def main():
    import streamlit as st

    st.set_page_config(page_title="Hosting — Forecast & Variance",
                       layout="wide", page_icon="📊")
    st.markdown(
        f"<h2 style='color:{config.NAVY};margin-bottom:0'>Hosting — "
        f"Revenue Forecasting &amp; Variance</h2>"
        f"<p style='color:#5b6470;margin-top:2px'>Bottom-up driver model: "
        f"revenue = average customers × ARPC</p>", unsafe_allow_html=True)

    # ── Sidebar controls ────────────────────────────────────────────
    st.sidebar.header("Data")
    up = st.sidebar.file_uploader("Upload monthly actuals (CSV/Excel)",
                                  type=["csv", "xlsx", "xls"])
    if up is not None:
        suffix = ".xlsx" if up.name.lower().endswith(("xlsx", "xls")) else ".csv"
        tmp = io.BytesIO(up.getvalue())
        actual = (pd.read_excel(tmp) if suffix == ".xlsx" else pd.read_csv(tmp))
        actual.columns = [c.strip() for c in actual.columns]
        missing = [c for c in config.REQUIRED_COLUMNS if c not in actual.columns]
        if missing:
            st.sidebar.error(f"File missing required columns: {missing}")
            st.stop()
        actual["month"] = pd.to_datetime(actual["month"])
        actual = actual.sort_values("month").reset_index(drop=True)
        st.sidebar.success(f"Loaded {len(actual)} months from {up.name}")
    else:
        actual = data.load_actuals()
        st.sidebar.caption("Using bundled sample actuals.")

    has_budget = data.has_budget(actual)

    st.sidebar.header("Forecast")
    horizon = st.sidebar.slider("Horizon (months)", 6, 36, 12, step=3)
    scenario_pick = st.sidebar.radio("Highlight scenario", ["base", "bear", "bull"],
                                     horizontal=True)

    st.sidebar.header("Driver overrides")
    sp = Fc.starting_point(actual)
    churn = st.sidebar.slider("Monthly churn rate", 0.02, 0.10,
                              float(round(sp.churn_rate, 3)), step=0.001, format="%.3f")
    arpc_g = st.sidebar.slider("Monthly ARPC growth", 0.0, 0.02,
                               float(config.HostingBaseline().arpc_growth_m),
                               step=0.001, format="%.3f")
    new_adds = st.sidebar.slider("Monthly gross adds (000s)", 80, 300,
                                 int(round(sp.new_customers / 1000)), step=5)

    ov = Fc.DriverOverrides(churn_rate=churn, arpc_growth_m=arpc_g,
                            new_customers=new_adds * 1000.0)
    fcs = Fc.forecast_all(actual, months=horizon, overrides=ov)

    # ── KPI row ─────────────────────────────────────────────────────
    if has_budget:
        bridge = V.volume_rate_bridge(actual, period="ttm")
        acc = V.accuracy_metrics(actual)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("TTM revenue", f"${bridge['actual_revenue']/1e6:,.1f}M",
                  f"{bridge['total_variance_pct']:+.1%} vs plan")
        c2.metric("Variance", f"${bridge['total_variance']/1e6:+,.1f}M", bridge["status"])
        c3.metric("Volume effect", f"${bridge['volume_effect']/1e6:+,.1f}M")
        c4.metric("Rate effect", f"${bridge['rate_effect']/1e6:+,.1f}M")
        c5.metric("Forecast MAPE", f"{acc['mape']:.1%}", f"bias {acc['bias_pct']:+.1%}",
                  delta_color="off")
    else:
        st.info("No budget columns in this file — variance analysis hidden, "
                "forecast still available.")
        bridge = acc = None

    # ── Charts ──────────────────────────────────────────────────────
    left, right = st.columns(2)
    with left:
        st.plotly_chart(_fig_forecast_vs_actual(actual, fcs), use_container_width=True)
    with right:
        st.plotly_chart(_fig_rollforward(actual), use_container_width=True)

    if has_budget:
        l2, r2 = st.columns(2)
        with l2:
            st.plotly_chart(_fig_bridge(bridge), use_container_width=True)
        with r2:
            td = Fc.topdown_check(actual, fcs["base"])
            st.subheader("Top-down vs bottom-up")
            st.markdown(_esc(
                f"Trailing-12 actual **${td['ttm_actual']/1e6:,.0f}M** grown "
                f"**+{td['yoy_growth']:.0%}** gives a top-down target of "
                f"**${td['topdown_target']/1e6:,.0f}M**. The bottom-up base-case "
                f"forecast totals **${td['bottomup_total']/1e6:,.0f}M**, a gap of "
                f"**{td['gap_pct']:+.1%}** "
                f"({'within' if td['agree'] else 'outside'} the "
                f"±{td['tolerance']:.0%} band)."
            ))
            st.subheader("Scenario 12M totals")
            st.dataframe(pd.DataFrame({
                "Scenario": [k.capitalize() for k in fcs],
                "Forecast revenue ($M)": [round(df['revenue'].sum() / 1e6, 1)
                                          for df in fcs.values()],
            }), hide_index=True, use_container_width=True)

            st.subheader("Key takeaways")
            for b in V.narrative(bridge, acc):
                st.markdown(_esc(f"- {b}"))

    # ── Forecast table + PDF export ─────────────────────────────────
    st.subheader(f"Forecast detail — {scenario_pick} scenario")
    show = fcs[scenario_pick][["month", "closing_customers", "arpc", "revenue"]].copy()
    show["month"] = show["month"].dt.strftime("%Y-%m")
    st.dataframe(show.style.format({
        "closing_customers": "{:,.0f}", "arpc": "${:.2f}", "revenue": "${:,.0f}"}),
        hide_index=True, use_container_width=True)

    if has_budget:
        if st.button("📄 Generate PDF executive summary"):
            totals = {k: float(df["revenue"].sum()) for k, df in fcs.items()}
            td = Fc.topdown_check(actual, fcs["base"])
            path = pdf_report.build_report(actual, scenario_totals=totals, topdown=td)
            with open(path, "rb") as fh:
                st.download_button("Download PDF", fh.read(),
                                   file_name="hosting_variance_summary.pdf",
                                   mime="application/pdf")
            st.success(f"PDF generated at {path}")


# Streamlit executes the module top-to-bottom; only render inside a real run.
def _running_in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


if _running_in_streamlit():
    main()
elif __name__ == "__main__":
    print("This is a Streamlit app. Launch it with:\n"
          "    streamlit run hosting_forecast/app.py")
