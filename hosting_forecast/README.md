# Hosting Revenue Forecasting & Variance Automation

A self-contained FP&A toolkit for a **Hosting** business. It builds a
bottom-up, driver-based revenue forecast, compares actuals to budget, decomposes
the revenue variance into **volume (customers) vs rate (ARPC)** effects, and
surfaces everything through a **Streamlit dashboard** and a one-page **PDF
executive summary**.

The forecasting math uses a standard driver-based Hosting revenue model:

```
churned       = opening_customers * churn_rate
closing       = opening + new - churned
avg_customers = (opening + closing) / 2
revenue       = avg_customers * ARPC
```

## What it demonstrates

- **Bottom-up driver forecasting** under bear / base / bull scenarios
- **Top-down vs bottom-up reconciliation** (agree within a 2% band)
- **Variance analysis** (actual vs plan) with favourable / unfavourable flags
- **Volume / rate (price-volume) variance bridge** that reconciles exactly
- **Forecast accuracy** (MAPE, bias)
- Productionised delivery: interactive dashboard + exportable PDF

## Quick start

```bash
pip install -r ../requirements.txt          # pandas, numpy, streamlit, plotly, reportlab

# 1. Generate the bundled sample actuals (36 months)
python -m hosting_forecast.data

# 2. Launch the dashboard
streamlit run hosting_forecast/app.py
```

The dashboard runs on the bundled sample out of the box. Upload your own monthly
file from the sidebar to reforecast on real data.

## Run the pieces standalone (CLI)

```bash
python -m hosting_forecast.data        # generate + preview sample actuals CSV
python -m hosting_forecast.forecast    # 12M forecast + top-down/bottom-up check
python -m hosting_forecast.variance    # variance table + volume/rate bridge + MAPE
python -m hosting_forecast.pdf_report  # write output/hosting_variance_summary.pdf
```

## Input data schema

One row per month. Templates in `sample_data/`:
`hosting_actuals_template.xlsx` (Excel; data on sheet 1, an Instructions sheet on
sheet 2; rebuild with `python -m hosting_forecast.excel_template`) or
`hosting_actuals.csv` (flat file). The loader reads the first worksheet.

| Column | Meaning |
|---|---|
| `month` | First of month, `YYYY-MM-01` |
| `opening_customers` | Customers at start of month |
| `new_customers` | Gross adds in month |
| `churned_customers` | Customers lost in month |
| `closing_customers` | Customers at end of month |
| `arpc` | Average revenue per customer, monthly $ |
| `revenue` | `avg_customers * arpc` |
| `budget_revenue` *(optional)* | Plan revenue for the month |
| `budget_customers` *(optional)* | Plan closing customers |
| `budget_arpc` *(optional)* | Plan ARPC |

Budget columns are optional: without them the forecast still runs, but the
variance bridge and PDF are skipped.

## Files

| File | Role |
|---|---|
| `config.py` | Hosting anchors, scenario deltas, paths, palette |
| `data.py` | Synthetic generator + CSV/Excel loader & validation |
| `forecast.py` | `DriverForecast` roll-forward, scenarios, top-down check |
| `variance.py` | Variance table, volume/rate bridge, MAPE/bias, narrative |
| `pdf_report.py` | Reportlab one-page executive summary |
| `app.py` | Streamlit dashboard (Plotly charts + PDF export) |

Outputs are written to `hosting_forecast/output/`.
