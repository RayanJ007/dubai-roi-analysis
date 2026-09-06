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
- Market data is cached in four process-local snapshots. Cold reads are serialized to prevent simultaneous page requests from duplicating million-row reads. Restart the API after replacing the prepared database. Model-supported category combinations are aggregated once per process.
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
