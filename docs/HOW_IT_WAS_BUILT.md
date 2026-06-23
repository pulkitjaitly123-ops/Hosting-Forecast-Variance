# How this was built

This document records the design intent, the architecture, and the exact steps
used to build and verify the toolkit, so the project can be understood, audited,
or extended without guesswork.

## 1. Goal

Turn a static, spreadsheet-style Hosting revenue model into a living automation
that:

1. forecasts revenue bottom-up from operational drivers,
2. measures actuals against the plan,
3. explains the variance in volume vs rate terms, and
4. delivers the result through both an interactive dashboard and a one-page PDF.

The toolkit had to run instantly on synthetic data (for demonstration) while also
accepting a real monthly actuals file (for repeated use).

## 2. The model

Revenue is built from a monthly customer roll-forward, identical in logic to a
driver-based three-statement model:

```
churned        = opening_customers x churn_rate
closing        = opening + new_customers - churned
avg_customers  = (opening + closing) / 2
revenue        = avg_customers x ARPC
```

Two design choices matter:

- **Average customers** (not closing) drive revenue, so a customer that joins or
  leaves mid-period is weighted correctly.
- **Scenarios adjust the drivers** (churn delta, gross-add factor, ARPC-growth
  factor) rather than a single growth rate, which keeps every scenario explainable
  in operational language.

### Variance decomposition (the analytical core)

Because `revenue = customers x ARPC`, the revenue variance versus plan splits into
three reconciling pieces:

```
volume effect = (actual_customers - plan_customers) x plan_ARPC
rate effect   = (actual_ARPC - plan_ARPC) x plan_customers
joint effect  = (actual_customers - plan_customers) x (actual_ARPC - plan_ARPC)
```

`volume + rate + joint` equals the total revenue variance exactly; the toolkit
prints the residual to prove it (it is ~0). This is the "what *caused* the
variance" answer FP&A is expected to give.

### Top-down vs bottom-up check

As a confidence test, the trailing-12-month actual revenue is grown by a
management YoY target (top-down) and compared with the summed next-12-month
bottom-up forecast. If the two land within a 2% band they are treated as
agreeing.

## 3. Architecture

A single Python package, `hosting_forecast/`, with one responsibility per module:

| Module | Responsibility |
|---|---|
| `config.py` | Hosting anchors (≈2.8M customers, ≈5% monthly churn, ≈$15 ARPC), scenario deltas, file paths, colour palette |
| `data.py` | Synthetic actuals generator (seasonality + noise + a clean budget plan) and a CSV/Excel loader with schema validation |
| `forecast.py` | `DriverForecast` roll-forward, scenario engine, driver overrides, top-down reconciliation |
| `variance.py` | Actual-vs-budget table, volume/rate bridge, MAPE/bias, plain-English narrative |
| `pdf_report.py` | ReportLab one-page executive summary (KPI strip, bridge table, outlook, takeaways) |
| `app.py` | Streamlit dashboard with Plotly charts and a PDF export button |

Design principles:

- **Pure functions for the math.** `forecast.py` and `variance.py` take and
  return DataFrames and dicts, so they are runnable and testable without any UI.
- **UI is a thin shell.** `app.py` only arranges inputs and renders the outputs of
  the pure modules.
- **Every module has a `__main__`** that runs a meaningful self-check, which
  doubles as the verification harness below.
- **Budget columns are optional**, so the same code path serves a forecast-only
  file and a full variance analysis.

## 4. Build order

The package was built and verified one module at a time, each proven before the
next was started:

1. `config.py` — anchors, scenarios, schema, paths.
2. `data.py` — generate 36 months of synthetic actuals + budget; validate schema.
3. `forecast.py` — roll-forward, scenarios, top-down check; confirm the forecast
   continues smoothly from the actuals tail.
4. `variance.py` — variance table and the volume/rate bridge; confirm the bridge
   reconciles to zero residual.
5. `pdf_report.py` — render the one-page PDF; confirm all sections populate.
6. `app.py` — wire the dashboard and charts; confirm it boots and renders.
7. README, requirements, and this document.

## 5. Verification performed

Each CLI entry point was run and its output inspected:

```bash
python -m hosting_forecast.data        # 36-month sample CSV generated and previewed
python -m hosting_forecast.forecast    # forecast continues from actuals; top-down vs
                                       # bottom-up agree within 2% (about -1.0% gap)
python -m hosting_forecast.variance    # bridge reconciles exactly (volume + rate +
                                       # joint = total variance; residual ~0)
python -m hosting_forecast.pdf_report  # PDF written; full text content confirmed
```

The Streamlit app was launched headless and opened in a browser to confirm it
serves cleanly, the charts render, and the scenario/driver controls update the
forecast. During this visual check one bug was found and fixed: Streamlit's
markdown interprets `$...$` as LaTeX math, which garbled the dollar amounts in the
narrative. Dollar signs in the markdown strings are now escaped, and the fix was
re-verified in the browser. The screenshots in `docs/screenshots/` were captured
from the running dashboard after that fix.

## 6. Extending it

- **Real data**: drop a monthly file matching the schema in the README and load it
  from the dashboard sidebar, or pass its path to `data.load_actuals`.
- **More segments**: the same driver pattern (customers x ARPU) generalises to
  Domains or Commerce; add a segment dimension to `data.py` and aggregate.
- **Excel export**: `variance.py` already returns tidy DataFrames, so an
  openpyxl writer can be added alongside the PDF with no change to the math.

## 7. Data and scope

All figures are synthetic and generated by `data.py` for demonstration only. The
project is not affiliated with GoDaddy Inc. and contains no proprietary or
confidential data.
