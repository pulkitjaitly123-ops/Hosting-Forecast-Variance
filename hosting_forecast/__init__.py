"""
Hosting — Revenue Forecasting & Variance Analysis automation.

A self-contained FP&A toolkit that builds a bottom-up, driver-based revenue
forecast for the Hosting segment, compares it to actuals and budget, decomposes
the revenue variance into volume (customers) vs rate (ARPC) effects, and surfaces
everything through a Streamlit dashboard plus a one-page PDF executive summary.

The forecasting math follows a standard driver-based Hosting revenue model:

    churned      = opening_customers * churn_rate
    closing      = opening_customers + new_customers - churned
    avg_customers= (opening + closing) / 2
    revenue      = avg_customers * arpc

Modules
-------
config       Hosting anchors, scenario deltas, file paths.
data         Synthetic actuals generator + CSV/Excel loader & validation.
forecast     DriverForecast roll-forward engine, scenarios, top-down check.
variance     Actual vs plan, volume/rate bridge, forecast accuracy (MAPE/bias).
pdf_report   Reportlab one-page executive variance summary.
app          Streamlit dashboard (run: streamlit run hosting_forecast/app.py).
"""

__version__ = "1.0.0"
