import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  BarChart3,
  Calculator,
  Gauge,
  Home,
  Info,
  LineChart,
  MapPinned,
  Search,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { api } from "./api";
import "./styles.css";

const pages = [
  { key: "home", label: "Home", icon: Home },
  { key: "market", label: "Market", icon: Activity },
  { key: "areas", label: "Areas", icon: MapPinned },
  { key: "predict", label: "Predict", icon: Gauge },
  { key: "roi", label: "ROI", icon: Calculator },
  { key: "opportunities", label: "Opportunities", icon: TrendingUp },
  { key: "performance", label: "Model", icon: BarChart3 },
];

const money = (value) =>
  value === null || value === undefined || Number.isNaN(value)
    ? "N/A"
    : `AED ${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const pct = (value) =>
  value === null || value === undefined || Number.isNaN(value)
    ? "N/A"
    : `${(Number(value) * 100).toFixed(2)}%`;

const titleCase = (value) =>
  String(value ?? "")
    .replaceAll("_", " ")
    .split(" ")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

function useAsync(factory, deps, enabled = true) {
  const [state, setState] = useState({ loading: enabled, data: null, error: null });

  useEffect(() => {
    if (!enabled) {
      setState((previous) => ({ ...previous, loading: false, error: null }));
      return undefined;
    }
    let active = true;
    setState((previous) => ({ ...previous, loading: true, error: null }));
    factory()
      .then((data) => active && setState({ loading: false, data, error: null }))
      .catch((error) => active && setState({ loading: false, data: null, error }));
    return () => {
      active = false;
    };
  }, [...deps, enabled]);

  return state;
}

function Metric({ label, value, hint }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}

function Notice({ title = "Research disclaimer", children }) {
  return (
    <div className="notice">
      <Info size={18} />
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}

function Definition({ title, children }) {
  return (
    <div className="definition">
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}

function LoadingCard({ label = "Loading dashboard data..." }) {
  return <div className="panel loading">{label}</div>;
}

function ErrorCard({ error }) {
  return <div className="panel error">{error.message}</div>;
}

function LineChartBox({ data, xKey, yKey, title, formatValue = (v) => v }) {
  const points = data ?? [];
  const width = 720;
  const height = 300;
  const pad = 34;
  const values = points.map((d) => Number(d[yKey] ?? 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const path = points
    .map((point, index) => {
      const x = pad + (index / Math.max(points.length - 1, 1)) * (width - pad * 2);
      const y = height - pad - ((Number(point[yKey]) - min) / span) * (height - pad * 2);
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  return (
    <div className="chart-card">
      <h3>{title}</h3>
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <defs>
          <linearGradient id={`${title}-line`} x1="0" x2="1">
            <stop offset="0%" stopColor="#43a7ff" />
            <stop offset="100%" stopColor="#ff8a2a" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((tick) => (
          <line
            key={tick}
            x1={pad}
            x2={width - pad}
            y1={pad + tick * ((height - pad * 2) / 3)}
            y2={pad + tick * ((height - pad * 2) / 3)}
            className="grid"
          />
        ))}
        <path d={path} fill="none" stroke={`url(#${title}-line)`} strokeWidth="4" />
        {points.slice(-1).map((point) => (
          <text key="last" x={width - pad} y={pad} textAnchor="end" className="chart-label">
            {formatValue(point[yKey])}
          </text>
        ))}
        <text x={pad} y={height - 8} className="chart-axis">
          {points[0]?.[xKey] ?? ""}
        </text>
        <text x={width - pad} y={height - 8} textAnchor="end" className="chart-axis">
          {points.at(-1)?.[xKey] ?? ""}
        </text>
      </svg>
    </div>
  );
}

function BarList({ data, title, valueKey, labelKey = "area_name_en", formatValue = (v) => v }) {
  const rows = (data ?? []).slice(0, 12);
  const max = Math.max(...rows.map((row) => Number(row[valueKey] ?? 0)), 1);
  return (
    <div className="panel">
      <h3>{title}</h3>
      <div className="bar-list">
        {rows.map((row) => (
          <div className="bar-row" key={row[labelKey]}>
            <span>{titleCase(row[labelKey])}</span>
            <div className="bar-track">
              <div style={{ width: `${(Number(row[valueKey]) / max) * 100}%` }} />
            </div>
            <strong>{formatValue(row[valueKey])}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function CoordinateMap({ areas, title }) {
  const mapped = (areas ?? []).filter((area) => area.latitude && area.longitude);
  const [selected, setSelected] = useState("all");
  const visible = selected === "all" ? mapped.slice(0, 50) : mapped.filter((area) => area.area_name_en === selected);

  const lats = mapped.map((area) => area.latitude);
  const lons = mapped.map((area) => area.longitude);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  const x = (lon) => ((lon - minLon) / (maxLon - minLon || 1)) * 88 + 6;
  const y = (lat) => 94 - ((lat - minLat) / (maxLat - minLat || 1)) * 82;

  return (
    <div className="panel map-panel">
      <div className="panel-head">
        <div>
          <h3>{title}</h3>
          <p>Coordinate view using approximate Dubai area centers. No external map API required.</p>
        </div>
        <label className="search-select">
          <Search size={16} />
          <select value={selected} onChange={(event) => setSelected(event.target.value)}>
            <option value="all">All mapped areas</option>
            {mapped.map((area) => (
              <option key={area.area_name_en} value={area.area_name_en}>
                {titleCase(area.area_name_en)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <svg className="coord-map" viewBox="0 0 100 100">
        <path d="M12 68 C25 45, 38 30, 60 21 C69 18, 78 19, 89 10" className="coast" />
        <path d="M10 76 C32 58, 55 44, 92 38" className="road" />
        <path d="M24 87 C40 69, 53 62, 84 57" className="road faint" />
        {visible.map((area) => (
          <g key={area.area_name_en}>
            <circle
              cx={x(area.longitude)}
              cy={y(area.latitude)}
              r={selected === area.area_name_en ? 3.9 : Math.max(1.5, Math.min(5, area.transactions / 4000))}
              className={selected === area.area_name_en ? "pin active" : "pin"}
            />
            <title>
              {titleCase(area.area_name_en)}: {area.transactions.toLocaleString()} transactions, {money(area.median_price)}
            </title>
            {(selected === area.area_name_en || visible.length < 20) && (
              <text x={x(area.longitude) + 2.2} y={y(area.latitude) - 1.4}>
                {titleCase(area.area_name_en)}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

function Filters({ options, filters, setFilters }) {
  return (
    <div className="filter-strip">
      <label>
        Years
        <select
          value={filters.year}
          onChange={(event) => setFilters((f) => ({ ...f, year: event.target.value }))}
        >
          <option value="">Latest available</option>
          {(options?.years ?? []).slice().reverse().map((year) => (
            <option key={year} value={year}>
              {year}
            </option>
          ))}
        </select>
      </label>
      <label>
        Property type
        <select
          value={filters.propertyType}
          onChange={(event) => setFilters((f) => ({ ...f, propertyType: event.target.value }))}
        >
          <option value="">All types</option>
          {(options?.property_types ?? []).map((type) => (
            <option key={type} value={type}>
              {titleCase(type)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Area
        <input
          list="area-list"
          value={filters.area}
          onChange={(event) => setFilters((f) => ({ ...f, area: event.target.value }))}
          placeholder="Search familiar areas"
        />
        <datalist id="area-list">
          {(options?.areas ?? []).map((area) => (
            <option key={area} value={area}>
              {titleCase(area)}
            </option>
          ))}
        </datalist>
      </label>
    </div>
  );
}

function filterParams(filters, minTransactions) {
  return {
    years: filters.year ? [Number(filters.year)] : undefined,
    property_types: filters.propertyType ? [filters.propertyType] : undefined,
    areas: filters.area ? [filters.area.toLowerCase()] : undefined,
    min_transactions: minTransactions,
  };
}

function HomePage({ overview, options }) {
  return (
    <section className="page-grid">
      <Notice>
        This dashboard is for research and education only. It is not financial, legal, tax, or investment advice.
      </Notice>
      <div className="metrics-grid">
        <Metric label="Rows in dashboard" value={overview?.metrics?.transactions?.toLocaleString() ?? "Loading"} />
        <Metric label="Known areas" value={(options?.areas?.length ?? 0).toLocaleString()} />
        <Metric label="Price model target" value="Log price" hint="Converted back to AED" />
        <Metric label="Deployment plan" value="Free-first" hint="Vercel + free backend option" />
      </div>
      <div className="panel narrative">
        <h2>How this works</h2>
        <p>
          The notebook cleaned Dubai real estate transaction records, narrowed the modeling set to residential sales,
          inferred selected missing room categories with CatBoost, and trained an XGBoost model to estimate transaction value.
        </p>
        <p>
          The app exposes that research through an API, so the frontend asks for compact summaries instead of loading the
          entire dataset. That is the main reason this architecture is better for deployment than the notebook or Streamlit prototype.
        </p>
      </div>
      <div className="definition-grid">
        <Definition title="Market">Track volume, median prices, and price per square metre.</Definition>
        <Definition title="Areas">Compare districts by activity, price, and typical property size.</Definition>
        <Definition title="Prediction">Estimate property value using the saved XGBoost model.</Definition>
        <Definition title="ROI">Convert predicted or manual purchase prices into yield scenarios.</Definition>
      </div>
    </section>
  );
}

function MarketPage({ overview, areas }) {
  if (!overview) return <LoadingCard />;
  return (
    <section className="page-grid">
      <Notice>Market metrics are based on cleaned transaction data and should be interpreted as historical evidence.</Notice>
      <div className="metrics-grid">
        <Metric label="Transactions" value={overview.metrics.transactions.toLocaleString()} />
        <Metric label="Median price" value={money(overview.metrics.median_price)} />
        <Metric label="Median area" value={`${Math.round(overview.metrics.median_area).toLocaleString()} sqm`} />
        <Metric label="Median price / sqm" value={money(overview.metrics.median_price_per_sqm)} />
      </div>
      <div className="two-col">
        <LineChartBox data={overview.monthly} xKey="month_start" yKey="transactions" title="Transaction Volume" formatValue={(v) => Number(v).toLocaleString()} />
        <LineChartBox data={overview.monthly} xKey="month_start" yKey="median_price" title="Median Price" formatValue={money} />
      </div>
      <BarList data={areas} title="Top areas by transaction count" valueKey="transactions" formatValue={(v) => Number(v).toLocaleString()} />
      <CoordinateMap areas={areas} title="Mapped market activity" />
    </section>
  );
}

function AreasPage({ areas }) {
  return (
    <section className="page-grid">
      <Definition title="Price per sqm">
        Price per square metre makes areas easier to compare when their typical property sizes differ.
      </Definition>
      <div className="two-col">
        <BarList data={areas} title="Median price by active area" valueKey="median_price" formatValue={money} />
        <BarList data={areas} title="Median price per sqm" valueKey="median_price_per_sqm" formatValue={money} />
      </div>
      <CoordinateMap areas={areas} title="Area comparison map" />
      <div className="panel table-panel">
        <h3>Area summary</h3>
        <table>
          <thead>
            <tr>
              <th>Area</th>
              <th>Transactions</th>
              <th>Median Price</th>
              <th>Price / sqm</th>
              <th>Median Area</th>
            </tr>
          </thead>
          <tbody>
            {(areas ?? []).slice(0, 30).map((area) => (
              <tr key={area.area_name_en}>
                <td>{titleCase(area.area_name_en)}</td>
                <td>{area.transactions.toLocaleString()}</td>
                <td>{money(area.median_price)}</td>
                <td>{money(area.median_price_per_sqm)}</td>
                <td>{Math.round(area.median_area).toLocaleString()} sqm</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PredictPage({ onPrediction }) {
  const [form, setForm] = useState({
    area_name_en: "",
    property_sub_type_en: "",
    property_type_en: "",
    property_usage_en: "",
    rooms_en: "",
    reg_type_en: "",
    procedure_name_en: "",
    has_parking: true,
    procedure_area: 100,
    year: 2026,
    month: 1,
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const scopes = useMemo(() => {
    const keys = [
      "area_name_en",
      "property_sub_type_en",
      "property_type_en",
      "property_usage_en",
      "rooms_en",
      "reg_type_en",
      "procedure_name_en",
    ];
    return Object.fromEntries(keys.filter((key) => form[key]).map((key) => [key, form[key]]));
  }, [form]);
  const optionState = useAsync(() => api.predictionOptions(scopes), [JSON.stringify(scopes)]);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const options = optionState.data ?? {};

  useEffect(() => {
    if (options.median_area && !Number.isNaN(options.median_area)) {
      setForm((current) => ({ ...current, procedure_area: Math.round(options.median_area) }));
    }
  }, [options.median_area]);

  async function submit(event) {
    event.preventDefault();
    setError(null);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).map(([key, value]) => [key, typeof value === "string" ? value.toLowerCase() : value])
      );
      const prediction = await api.predictPrice(payload);
      setResult(prediction);
      onPrediction(prediction.predicted_price);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="page-grid">
      <Notice title="Prediction disclaimer">
        The model estimates value from historical records. It does not know exact condition, floor, view, finishing, negotiation, or live sentiment.
      </Notice>
      <Definition title="Why inputs are guided">
        XGBoost only accepts categories it saw during training, so the form narrows choices as you go.
      </Definition>
      <form className="predict-form panel" onSubmit={submit}>
        <Field label="Area" value={form.area_name_en} options={options.area_name_en} onChange={(v) => update("area_name_en", v)} />
        <Field label="Subtype" value={form.property_sub_type_en} options={options.property_sub_type_en} onChange={(v) => update("property_sub_type_en", v)} />
        <Field label="Type" value={form.property_type_en} options={options.property_type_en} onChange={(v) => update("property_type_en", v)} />
        <Field label="Usage" value={form.property_usage_en} options={options.property_usage_en} onChange={(v) => update("property_usage_en", v)} />
        <Field label="Rooms" value={form.rooms_en} options={options.rooms_en} onChange={(v) => update("rooms_en", v)} />
        <Field label="Registration" value={form.reg_type_en} options={options.reg_type_en} onChange={(v) => update("reg_type_en", v)} />
        <Field label="Procedure" value={form.procedure_name_en} options={options.procedure_name_en} onChange={(v) => update("procedure_name_en", v)} />
        <label>
          Property area sqm
          <input type="number" min="1" value={form.procedure_area} onChange={(e) => update("procedure_area", Number(e.target.value))} />
        </label>
        <label>
          Year
          <input type="number" min="2000" max="2035" value={form.year} onChange={(e) => update("year", Number(e.target.value))} />
        </label>
        <label>
          Month
          <select value={form.month} onChange={(e) => update("month", Number(e.target.value))}>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((month) => (
              <option key={month} value={month}>
                {new Date(2026, month - 1).toLocaleString("en", { month: "long" })}
              </option>
            ))}
          </select>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={form.has_parking} onChange={(e) => update("has_parking", e.target.checked)} />
          Has parking
        </label>
        <button className="primary" type="submit">Predict price</button>
      </form>
      {error && <ErrorCard error={error} />}
      {result && (
        <div className="metrics-grid">
          <Metric label="Predicted price" value={money(result.predicted_price)} />
          <Metric label="Predicted price / sqm" value={money(result.predicted_price_per_sqm)} />
          <Metric label="Similar median" value={money(result.similar_median_price)} />
          <Metric label="Comparable records" value={result.similar_count.toLocaleString()} />
          <Metric label="Model area used" value={titleCase(result.advertised_area_used)} />
        </div>
      )}
    </section>
  );
}

function Field({ label, value, options = [], onChange }) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)} required>
        <option value="">Choose {label.toLowerCase()}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {titleCase(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

function RoiPage({ defaultPrice }) {
  const [form, setForm] = useState({
    purchase_price: defaultPrice ?? 1000000,
    monthly_rent: 7500,
    annual_costs: 15000,
    closing_cost_rate: 0.04,
    vacancy_rate: 0.05,
    appreciation_rate: 0.03,
  });
  const state = useAsync(() => api.roi(form), [JSON.stringify(form)]);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: Number(value) }));

  return (
    <section className="page-grid">
      <Notice title="ROI disclaimer">ROI is a scenario calculation, not a return guarantee.</Notice>
      <Definition title="Net yield">
        Net yield subtracts estimated annual costs and accounts for acquisition costs, so it is more realistic than gross yield.
      </Definition>
      <div className="predict-form panel">
        {Object.entries(form).map(([key, value]) => (
          <label key={key}>
            {titleCase(key)}
            <input step="0.01" type="number" value={value} onChange={(event) => update(key, event.target.value)} />
          </label>
        ))}
      </div>
      {state.data && (
        <div className="metrics-grid">
          <Metric label="Gross yield" value={pct(state.data.gross_yield)} />
          <Metric label="Net yield" value={pct(state.data.net_yield)} />
          <Metric label="Annual net income" value={money(state.data.annual_net_income)} />
          <Metric label="One-year ROI" value={pct(state.data.one_year_roi)} />
        </div>
      )}
    </section>
  );
}

function OpportunitiesPage({ opportunities }) {
  return (
    <section className="page-grid">
      <Definition title="Value score">
        A screening score that rewards high transaction activity and lower median price per square metre. It is a shortlist tool, not investment advice.
      </Definition>
      <BarList data={opportunities} title="Opportunity score by area" valueKey="value_score" formatValue={(v) => Number(v).toFixed(2)} />
      <div className="panel table-panel">
        <table>
          <thead>
            <tr>
              <th>Area</th>
              <th>Score</th>
              <th>Transactions</th>
              <th>Price / sqm</th>
            </tr>
          </thead>
          <tbody>
            {(opportunities ?? []).map((area) => (
              <tr key={area.area_name_en}>
                <td>{titleCase(area.area_name_en)}</td>
                <td>{Number(area.value_score).toFixed(2)}</td>
                <td>{area.transactions.toLocaleString()}</td>
                <td>{money(area.median_price_per_sqm)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PerformancePage() {
  const state = useAsync(api.performance, []);
  if (state.loading) return <LoadingCard />;
  if (state.error) return <ErrorCard error={state.error} />;
  const perf = state.data;
  return (
    <section className="page-grid">
      <Notice title="Model disclaimer">
        Model performance is historical validation evidence. Real-world future accuracy depends on market drift and missing property details.
      </Notice>
      <div className="metrics-grid">
        <Metric label="Rooms accuracy" value={perf.rooms_model.accuracy.toFixed(4)} />
        <Metric label="Rooms macro F1" value={perf.rooms_model.macro_f1.toFixed(4)} />
        <Metric label="Price MAE" value={money(perf.price_model.mae)} />
        <Metric label="Price R2" value={perf.price_model.r2.toFixed(4)} />
      </div>
      <ImageGrid figures={perf.figures} />
    </section>
  );
}

function ImageGrid({ figures }) {
  return (
    <div className="image-grid">
      {Object.entries(figures).map(([label, src]) => (
        <figure key={label} className="panel">
          <img src={`${api.base}${src}`} alt={titleCase(label)} />
          <figcaption>{titleCase(label)}</figcaption>
        </figure>
      ))}
    </div>
  );
}

function App() {
  const [page, setPage] = useState("home");
  const [filters, setFilters] = useState({ year: "", propertyType: "", area: "" });
  const [predictedPrice, setPredictedPrice] = useState(null);
  const [minTransactions, setMinTransactions] = useState(100);

  const optionsState = useAsync(api.options, []);
  const params = filterParams(filters, minTransactions);
  const needsOverview = ["home", "market"].includes(page);
  const needsAreas = ["market", "areas"].includes(page);
  const needsOpportunities = page === "opportunities";
  const overviewState = useAsync(() => api.overview(params), [JSON.stringify(params)], needsOverview);
  const areasState = useAsync(() => api.areas(params), [JSON.stringify(params)], needsAreas);
  const oppState = useAsync(() => api.opportunities(params), [JSON.stringify(params)], needsOpportunities);
  const showMarketFilters = ["market", "areas", "opportunities"].includes(page);

  return (
    <main>
      <section className="hero">
        <div>
          <span className="eyebrow">Dubai Transaction Intelligence</span>
          <h1>Dubai Real Estate Dashboard</h1>
          <p>
            A dark analytical workspace for market movement, area comparison, price prediction, and ROI planning.
          </p>
          <div className="pill-row">
            <span>FastAPI backend</span>
            <span>React frontend</span>
            <span>Saved ML models</span>
            <span>No paid map API</span>
          </div>
        </div>
        <div className="hero-card">
          <Sparkles />
          <strong>Prototype to production path</strong>
          <p>Local demo first. Free deployment when ready.</p>
        </div>
      </section>

      <nav className="top-nav">
        {pages.map(({ key, label, icon: Icon }) => (
          <button key={key} className={page === key ? "active" : ""} onClick={() => setPage(key)}>
            <Icon size={16} />
            {label}
          </button>
        ))}
      </nav>

      {showMarketFilters && (
        <>
          <Filters options={optionsState.data} filters={filters} setFilters={setFilters} />
          <div className="mini-filter">
            <label>
              Minimum area transactions
              <input type="range" min="25" max="1000" step="25" value={minTransactions} onChange={(e) => setMinTransactions(Number(e.target.value))} />
              <span>{minTransactions}</span>
            </label>
          </div>
        </>
      )}

      {needsOverview && overviewState.error && <ErrorCard error={overviewState.error} />}
      {needsAreas && areasState.error && <ErrorCard error={areasState.error} />}

      {page === "home" && <HomePage overview={overviewState.data} options={optionsState.data} />}
      {page === "market" && <MarketPage overview={overviewState.data} areas={areasState.data} />}
      {page === "areas" && <AreasPage areas={areasState.data ?? []} />}
      {page === "predict" && <PredictPage onPrediction={setPredictedPrice} />}
      {page === "roi" && <RoiPage defaultPrice={predictedPrice} />}
      {page === "opportunities" && <OpportunitiesPage opportunities={oppState.data ?? []} />}
      {page === "performance" && <PerformancePage />}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
