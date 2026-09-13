# React / FastAPI application

Run from the repository root, with the prepared `data/dashboard.sqlite` and saved models available:

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
.venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. `VITE_API_BASE` can override the API address. The legacy Streamlit app remains separate.

## Analysis behavior

- Overview is an unfiltered summary of valid registered **sales** from the prepared database. Mortgages and gifts are excluded from pricing and comparable-sale analysis.
- Market, Areas and Discover share applied filters. Years form an inclusive range; types and official area names are repeated query parameters (OR within each list, AND between filters). Familiar-area aliases only resolve to names present in the data. Empty matching years return no results.
- Transaction price bounds are inclusive and uncapped by the UI. Minimum area records applies to area tables, map markers and screening scores, not the market-wide totals.
- Area price comparisons use the selected market's median individual AED/sqm. Screening scores equally weight activity and affordability percentile ranks among qualifying areas. They are not estimates of rental return or mispricing.
- Market responses are cached for eight filter combinations; transaction tables are never cached in Python. SQLite uses disk-backed temporary tables and a small page cache. Exact quantiles stream one group into a numeric buffer capped at 32 MiB, then partition it in place; larger groups use exact disk-based order statistics. No sampling or approximate medians are used. Expensive requests and cold model loading are serialized to bound overlapping allocations. Restart the API after replacing the prepared database. Model-supported category combinations are aggregated once per process.
- Dataset dates are shown as recorded, including future-dated source records. No claim is made that the snapshot is live or that the latest year is complete. Review source-date parsing before using it as a live feed.

## Valuation and ROI

Valuation estimates registered value at a historical reference date. Comparable evidence matches area, type, subtype, rooms, registration, size within ±25%, and the 36 months ending in the selected month. Below ten matches, median and quartile bands are withheld. The observed quartile band is not a calibrated prediction interval.

The valuation can be sent to ROI as a separate starting market value; the optional asking price becomes the purchase price. The user controls growth, rent, vacancy, annual costs, purchase costs, selling costs and holding period. Values persist while navigating between pages, until reload.

Future value = starting value × (1 + assumed growth)^years.

Net profit = future value × (1 − selling cost rate) + annual net rent × years − total acquisition cost.

Total ROI = net profit / total acquisition cost. Returns are cumulative, not annualized. This is an unlevered scenario with constant rent and costs; financing, taxes and rent reinvestment are excluded. The regressor is not a validated forecasting model. ±3 percentage point sensitivities are assumptions, not forecast probabilities.

## Map

Leaflet 1.9.4 uses OpenStreetMap raster tiles with visible attribution and no API key. Tile requests require an internet connection. Approximate area-centre coordinates come from the project's existing lookup, supplemented only by unambiguous matches from its alias file; unmapped areas remain in tables. This is not a boundary or individual-property map.

For public deployment, follow the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/) and select a suitable provider if traffic grows. The implementation follows the [Leaflet quick start](https://leafletjs.com/examples/quick-start/).

## Verification

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
.venv/Scripts/python.exe -m unittest discover -s backend/tests -v
cd frontend
npm run build
npx prettier --check src index.html package.json
```

Backend tests use temporary SQLite fixtures rather than modifying the prepared database. Saved notebook model metrics are displayed with explanations; they are not a fresh evaluation or a time-based backtest.

## Render deployment with limited memory

Use the repository root as the Render service's root directory. Set its **Build Command** to:

```sh
pip install -r backend/requirements.txt && python -m backend.prepare_deployment
```

Set its **Start Command** to:

```sh
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

The build converts the original JSON model to XGBoost's UBJSON representation and verifies the complete model state survives the round trip. This preserves every tree, categorical mapping and saved model attribute; there is no retraining, pruning or reduced precision. Conversion runs during build because parsing the original JSON has a large transient memory cost. The generated `.ubj` file is ignored by Git and included in the built service. Render runtime requires this artifact instead of silently loading the expensive JSON file. See [XGBoost model formats](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html). Render's [build pipeline runs on separate compute](https://render.com/docs/build-pipeline), outside the live web instance's RAM limit.

The build also downloads the prepared database, if needed, and calculates exact summaries for all years, the latest year, and the latest three data years. These small responses are stored in `data/market_summaries.json` so common page requests do not need a cold full-table scan. The artifact includes a SHA-256 signature of the database and calculation code; mismatched or damaged artifacts fall back to live calculations. All generated files stay out of Git and become part of the Render build. Other filters still query the actual matching transactions.

Keep `DASHBOARD_DB_URL` set to the direct download URL of the prepared SQLite database, with `DASHBOARD_DATA_TOKEN` only if the download requires it. Downloads stream in 1 MiB chunks and publish the file only after completion. A PostgreSQL connection string is not a download URL. Missing data now raises an explicit configuration error instead of attempting to rebuild millions of raw CSV rows in the web process.

Vercel builds use `/api` on the frontend's own origin. `frontend/vercel.json` forwards those requests (including valuation POSTs and figure requests) to the Render backend. This avoids browser CORS failures when production and preview hostnames differ. Local development and other hosts still use `VITE_API_BASE`. If the Render backend URL changes, update the rewrite destination. Direct cross-origin clients can use `CORS_ALLOWED_ORIGINS`, a comma-separated origin list; the production Vercel origin is also explicitly allowed in the backend.

Use one worker: additional worker processes each load a separate model and cache. The saved regressor is loaded lazily, once per process, and inference uses one CPU thread. Its feature preparation, category alignment, log-price inversion, reference-date validation, comparables and ROI behavior are preserved.

The first custom market filter requires an exact scan and can be slower on a small instance; repeated requests use the cached summaries. SQLite temporary files need writable disk space. Local process-RSS measurements are not a guarantee of Render container usage; verify Render memory metrics after deployment, including valuation and several different filters.

To reproduce full-data memory measurements and verify predictions against the original JSON model locally:

```powershell
.venv/Scripts/python.exe -m backend.prepare_deployment
.venv/Scripts/python.exe -m backend.benchmark_memory
$env:RUN_MODEL_INTEGRATION = '1'
.venv/Scripts/python.exe -m unittest backend.tests.test_model_integration -v
```

These optional checks require the real local database, saved model and development dependencies. The integration test compares 256 actual input rows with the original model, checks representative API predictions, and verifies model values flow into ROI unchanged.

Local verification on the 1,336,373-sale snapshot (Windows, September 2026):

| Workload | Peak process RSS |
| --- | ---: |
| Previous full-market overview and areas | 810.2 MiB |
| Prepared overview and areas | 114.8 MiB |
| Overview, real model, valuation, ROI, and custom two-year filter | 410.5 MiB |

All full-dataset overview and area values matched the previous implementation (floating-point totals compared with tolerance). All 17 tests passed with the real-model integration check enabled. The prepared overview request took 0.47 seconds, cached requests 0.004–0.033 seconds, and the custom two-year filter 9.59 seconds locally. Request timings exclude interpreter startup and the benchmark's initial general-options lookup; hosting CPU and disk speed will change these timings.
