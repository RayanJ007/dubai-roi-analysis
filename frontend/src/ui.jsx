import React, { useEffect, useRef, useState } from "react";
import {
  ArrowDownUp,
  ChevronDown,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export const number = (v) =>
  v == null || !Number.isFinite(Number(v))
    ? "—"
    : Number(v).toLocaleString("en", { maximumFractionDigits: 0 });
export const money = (v) => (v == null ? "—" : `AED ${number(v)}`);
export const compact = (v) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("en", {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(v);
export const pct = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
export const signedPct = (v) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${pct(v)}`;
export const titleCase = (v) =>
  String(v ?? "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
export const initialFilters = {
  start: "",
  end: "",
  types: [],
  areas: [],
  minPrice: "",
  maxPrice: "",
  minTransactions: 100,
};
export function useAsync(factory, deps, enabled = true) {
  const [state, setState] = useState({
    loading: enabled,
    data: null,
    error: null,
  });
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    setState({ loading: true, data: null, error: null });
    Promise.resolve()
      .then(factory)
      .then((data) => active && setState({ loading: false, data, error: null }))
      .catch(
        (error) => active && setState({ loading: false, data: null, error }),
      );
    return () => {
      active = false;
    };
  }, [...deps, enabled]);
  return state;
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <span className="loading-dot" />
      Reading the transaction data…
    </div>
  );
}
export function ErrorCard({ error }) {
  return (
    <div className="error" role="alert">
      {error.message || "Unable to load data. Please try again."}
    </div>
  );
}
export function Empty({
  children = "No transactions match these filters. Widen the date or price range, or clear a selection.",
}) {
  return <div className="empty">{children}</div>;
}
export function Metric({ label, value, hint }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}
export function Note({ title, children }) {
  return (
    <div className="note">
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
export function SectionHead({ kicker, title, children }) {
  return (
    <div className="section-head">
      <div>
        {kicker && <span className="eyebrow">{kicker}</span>}
        <h2>{title}</h2>
      </div>
      {children}
    </div>
  );
}

export function Chart({
  data = [],
  xKey,
  yKey,
  title,
  format = number,
  color = "#55b5ff",
}) {
  const [hover, setHover] = useState(null);
  const points = data.filter(
    (p) => p[yKey] != null && Number.isFinite(Number(p[yKey])),
  );
  const width = 760,
    height = 270,
    left = 75,
    right = 22,
    top = 28,
    bottom = 38;
  const values = points.map((p) => Number(p[yKey])),
    min = Math.min(0, ...values),
    max = Math.max(...values, 1),
    span = max - min || 1;
  const xValues = points.map((p) =>
    xKey === "month_start" ? Date.parse(p[xKey]) : Number(p[xKey]),
  );
  const firstX = xValues[0],
    xSpan = xValues.at(-1) - firstX || 1;
  const x = (i) =>
    left +
    (points.length === 1 ? 0.5 : (xValues[i] - firstX) / xSpan) *
      (width - left - right);
  const y = (v) => top + (1 - (v - min) / span) * (height - top - bottom);
  const selected =
    points[Math.min(hover ?? points.length - 1, points.length - 1)];
  const label = (v) =>
    String(v).length >= 10 ? String(v).slice(0, 7) : String(v);
  return (
    <div className="panel chart-card">
      <div className="chart-head">
        <h3>{title}</h3>
        <div>
          <strong>{selected ? format(selected[yKey]) : "—"}</strong>
          <small>{selected ? label(selected[xKey]) : "No data"}</small>
        </div>
      </div>
      {!points.length ? (
        <Empty />
      ) : (
        <>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`${title}: ${points.length} observations`}
          >
            {[0, 1, 2, 3].map((t) => (
              <g key={t}>
                <line
                  x1={left}
                  x2={width - right}
                  y1={y(min + (span * t) / 3)}
                  y2={y(min + (span * t) / 3)}
                  className="grid"
                />
                <text
                  x={left - 12}
                  y={y(min + (span * t) / 3) + 4}
                  textAnchor="end"
                  className="chart-axis"
                >
                  {compact(min + (span * t) / 3)}
                </text>
              </g>
            ))}
            <path
              d={points
                .map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[yKey])}`)
                .join(" ")}
              fill="none"
              stroke={color}
              strokeWidth="3"
              strokeLinejoin="round"
            />
            {points.map((p, i) => (
              <g key={i}>
                <circle
                  cx={x(i)}
                  cy={y(p[yKey])}
                  r={points.length < 25 || hover === i ? 3.5 : 0}
                  fill={color}
                />
                <rect
                  x={
                    x(i) -
                    Math.max(4, (width - left - right) / points.length / 2)
                  }
                  y={top}
                  width={Math.max(8, (width - left - right) / points.length)}
                  height={height - top - bottom}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  <title>
                    {label(p[xKey])}: {format(p[yKey])}
                  </title>
                </rect>
              </g>
            ))}
            <text x={left} y={height - 8} className="chart-axis">
              {label(points[0][xKey])}
            </text>
            <text
              x={width - right}
              y={height - 8}
              textAnchor="end"
              className="chart-axis"
            >
              {label(points.at(-1)[xKey])}
            </text>
          </svg>
          <details className="chart-data">
            <summary>View data table</summary>
            <div className="scroll-table">
              <table>
                <thead>
                  <tr>
                    <th>Period</th>
                    <th>{title}</th>
                  </tr>
                </thead>
                <tbody>
                  {points.map((p, i) => (
                    <tr key={i}>
                      <td>{label(p[xKey])}</td>
                      <td>{format(p[yKey])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
export function Bars({
  data = [],
  title,
  valueKey = "transactions",
  labelKey = "area_name_en",
  format = number,
}) {
  const rows = data.slice(0, 8),
    max = Math.max(...rows.map((r) => r[valueKey]), 1);
  return (
    <div className="panel">
      <h3>{title}</h3>
      {rows.length ? (
        <div className="bar-list">
          {rows.map((r) => (
            <div className="bar-row" key={r[labelKey]}>
              <div>
                <span>{titleCase(r[labelKey])}</span>
                <strong>{format(r[valueKey])}</strong>
              </div>
              <div className="bar-track">
                <div style={{ width: `${(r[valueKey] / max) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty />
      )}
    </div>
  );
}
export function MarketMap({ areas = [] }) {
  const container = useRef(null),
    mapRef = useRef(null),
    markers = useRef(null);
  const [tileError, setTileError] = useState(false);
  const mapped = areas.filter(
    (a) => Number.isFinite(a.latitude) && Number.isFinite(a.longitude),
  );
  useEffect(() => {
    const map = L.map(container.current, { scrollWheelZoom: false }).setView(
      [25.13, 55.25],
      11,
    );
    mapRef.current = map;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    })
      .on("tileerror", () => setTileError(true))
      .on("tileload", () => setTileError(false))
      .addTo(map);
    markers.current = L.layerGroup().addTo(map);
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);
  useEffect(() => {
    if (!mapRef.current) return;
    markers.current.clearLayers();
    mapped.forEach((a) => {
      const popup = document.createElement("div"),
        heading = document.createElement("strong"),
        content = document.createElement("p");
      heading.textContent = titleCase(a.area_name_en);
      content.textContent = `${number(a.transactions)} transactions · ${money(a.median_price)} median · ${money(a.median_price_per_sqm)}/sqm`;
      popup.append(heading, content);
      L.circleMarker([a.latitude, a.longitude], {
        radius: Math.min(22, 5 + Math.sqrt(a.transactions) / 24),
        color: "#0874c4",
        fillColor: "#219bfa",
        fillOpacity: 0.65,
        weight: 2,
      })
        .bindPopup(popup)
        .addTo(markers.current);
    });
    if (mapped.length)
      mapRef.current.fitBounds(
        mapped.map((a) => [a.latitude, a.longitude]),
        { padding: [35, 35], maxZoom: 13 },
      );
  }, [areas]);
  return (
    <div className="panel map-panel">
      <SectionHead kicker="Geography" title="Mapped market activity">
        <span className="subtle">
          {mapped.length} of {areas.length} areas mapped
        </span>
      </SectionHead>
      <div
        ref={container}
        className="market-map"
        aria-label="Interactive street map of Dubai market activity"
      />
      {tileError && (
        <p className="map-error" role="status">
          Street tiles could not load. Check your connection; area statistics
          remain available in the tables.
        </p>
      )}
      <p className="footnote">
        Circle size reflects transaction count. Locations are approximate area
        centres, not individual properties. {areas.length - mapped.length} areas
        have no coordinate match and remain in the tables.
      </p>
    </div>
  );
}
function MultiSelect({
  label,
  options = [],
  aliases = {},
  selected,
  onChange,
}) {
  const [search, setSearch] = useState("");
  const ref = useRef(null);
  const visible = options.filter((o) =>
    [o, ...(aliases[o] ?? [])]
      .join(" ")
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  useEffect(() => {
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target))
        ref.current.open = false;
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  return (
    <div className="multi-select">
      <span className="field-label">{label}</span>
      <details
        ref={ref}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            ref.current.open = false;
            ref.current.querySelector("summary").focus();
          }
        }}
      >
        <summary>
          {selected.length
            ? `${selected.length} selected`
            : `All ${label.toLowerCase()}`}
          <ChevronDown size={15} />
        </summary>
        <div className="select-popover">
          <label className="search-box">
            <Search size={16} />
            <input
              aria-label={`Search ${label.toLowerCase()}`}
              placeholder={`Search ${label.toLowerCase()}…`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <div className="select-options">
            {visible.length ? (
              visible.map((o) => (
                <label key={o}>
                  <input
                    type="checkbox"
                    checked={selected.includes(o)}
                    onChange={() =>
                      onChange(
                        selected.includes(o)
                          ? selected.filter((v) => v !== o)
                          : [...selected, o],
                      )
                    }
                  />
                  <span>
                    {titleCase(o)}
                    {aliases[o]?.length > 0 && (
                      <small className="alias-hint">
                        {aliases[o].slice(0, 2).map(titleCase).join(" · ")}
                      </small>
                    )}
                  </span>
                </label>
              ))
            ) : (
              <p>No matching areas or types in the data.</p>
            )}
          </div>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              ref.current.open = false;
            }}
          >
            Done
          </button>
        </div>
      </details>
      {selected.length > 0 && (
        <div className="tags">
          {selected.map((o) => (
            <button
              key={o}
              type="button"
              onClick={() => onChange(selected.filter((v) => v !== o))}
              aria-label={`Remove ${titleCase(o)}`}
            >
              {titleCase(o)}
              <X size={12} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
export function Filters({ options, value, onApply }) {
  const [draft, setDraft] = useState(value),
    years = options.years,
    first = years[0],
    last = years.at(-1);
  const start = Number(draft.start || first),
    end = Number(draft.end || last);
  const update = (k, v) => setDraft((c) => ({ ...c, [k]: v }));
  const changed = JSON.stringify(draft) !== JSON.stringify(value);
  return (
    <form
      className="filters"
      onSubmit={(e) => {
        e.preventDefault();
        onApply(draft);
      }}
    >
      <div className="filter-main">
        <div className="year-filter">
          <span className="field-label">
            Transaction years{" "}
            <strong>
              {start}–{end}
            </strong>
          </span>
          <div className="year-inputs">
            <input
              aria-label="Start year"
              type="number"
              min={first}
              max={end}
              value={start}
              onChange={(e) => update("start", e.target.value)}
              required
            />
            <span>to</span>
            <input
              aria-label="End year"
              type="number"
              min={start}
              max={last}
              value={end}
              onChange={(e) => update("end", e.target.value)}
              required
            />
          </div>
          <div className="year-sliders">
            <input
              aria-label="Start year slider"
              type="range"
              min={first}
              max={last}
              value={start}
              onChange={(e) =>
                update("start", Math.min(Number(e.target.value), end))
              }
            />
            <input
              aria-label="End year slider"
              type="range"
              min={first}
              max={last}
              value={end}
              onChange={(e) =>
                update("end", Math.max(Number(e.target.value), start))
              }
            />
          </div>
        </div>
        <MultiSelect
          label="Property types"
          options={options.property_types}
          selected={draft.types}
          onChange={(v) => update("types", v)}
        />
        <MultiSelect
          label="Areas"
          options={options.areas}
          aliases={options.area_aliases}
          selected={draft.areas}
          onChange={(v) => update("areas", v)}
        />
        <div className="filter-actions">
          <button className="primary" type="submit">
            <SlidersHorizontal size={15} />
            Apply filters
          </button>
          <button
            className="text-button"
            type="button"
            onClick={() => {
              setDraft(initialFilters);
              onApply(initialFilters);
            }}
          >
            Reset all
          </button>
        </div>
      </div>
      <details className="advanced-filters">
        <summary>
          Price range & sample size <ChevronDown size={14} />
        </summary>
        <div className="advanced-grid">
          <label>
            Minimum transaction value · AED
            <input
              type="number"
              min="0"
              step="any"
              value={draft.minPrice}
              placeholder="No minimum"
              onChange={(e) => update("minPrice", e.target.value)}
            />
          </label>
          <label>
            Maximum transaction value · AED
            <input
              type="number"
              min={draft.minPrice || 1}
              step="any"
              value={draft.maxPrice}
              placeholder={`No cap · data up to ${compact(options.coverage?.max_price)}`}
              onChange={(e) => update("maxPrice", e.target.value)}
            />
          </label>
          <label>
            Minimum records per area
            <input
              type="number"
              min="1"
              step="1"
              required
              value={draft.minTransactions}
              onChange={(e) =>
                update("minTransactions", Number(e.target.value))
              }
            />
          </label>
        </div>
        <p className="footnote">
          Price limits apply to individual transactions on this page. Sample
          size controls which areas appear in rankings, tables and maps; it does
          not remove transactions from market totals. No upper limit on sample
          size.
        </p>
      </details>
      <div className="filter-status">
        {changed
          ? "Selections changed · apply to update the results"
          : `${start}–${end} · ${draft.types.length ? draft.types.map(titleCase).join(", ") : "All property types"} · ${draft.areas.length ? `${draft.areas.length} selected areas` : "All areas"} · ${money(draft.minPrice || 0)} to ${draft.maxPrice ? money(draft.maxPrice) : "no price cap"} · Areas with ${number(draft.minTransactions)}+ records`}
      </div>
    </form>
  );
}
export function paramsFor(f, years = []) {
  const start = Number(f.start || years[0]),
    end = Number(f.end || years.at(-1));
  return {
    years:
      f.start || f.end
        ? Array.from(
            { length: Math.max(0, end - start + 1) },
            (_, i) => start + i,
          )
        : [],
    property_types: f.types,
    areas: f.areas,
    min_price: Number(f.minPrice || 0),
    max_price: f.maxPrice ? Number(f.maxPrice) : undefined,
    min_transactions: f.minTransactions,
  };
}
export function AreaTable({ areas, discover = false }) {
  const [sort, setSort] = useState({
    key: discover ? "value_score" : "transactions",
    desc: true,
  });
  const rows = [...areas].sort(
    (a, b) =>
      (Number(a[sort.key]) - Number(b[sort.key])) * (sort.desc ? -1 : 1),
  );
  const headings = discover
    ? [
        ["value_score", "Screening score"],
        ["transactions", "Transactions"],
        ["median_price_per_sqm", "AED / sqm"],
        ["price_vs_market", "Vs market / sqm"],
        ["off_plan_share", "Off-plan"],
      ]
    : [
        ["transactions", "Transactions"],
        ["median_price", "Median · AED"],
        ["median_price_per_sqm", "AED / sqm"],
        ["market_share", "Activity share"],
        ["off_plan_share", "Off-plan"],
      ];
  return (
    <div className="panel table-panel">
      <h3>
        {discover ? "Your area shortlist" : "Compare every qualifying area"}
      </h3>
      {!rows.length ? (
        <Empty>
          No areas meet this sample threshold. Reduce the minimum records per
          area or widen your selection.
        </Empty>
      ) : (
        <>
          <div className="scroll-table">
            <table>
              <thead>
                <tr>
                  <th>Area</th>
                  {headings.map(([key, label]) => (
                    <th
                      key={key}
                      aria-sort={
                        sort.key === key
                          ? sort.desc
                            ? "descending"
                            : "ascending"
                          : "none"
                      }
                    >
                      <button
                        onClick={() =>
                          setSort({
                            key,
                            desc: sort.key === key ? !sort.desc : true,
                          })
                        }
                      >
                        {label}
                        <ArrowDownUp size={12} />
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.area_name_en}>
                    <td>
                      <strong>{titleCase(a.area_name_en)}</strong>
                      <small>
                        Middle 50%: {compact(a.price_p25)}–
                        {compact(a.price_p75)} AED
                      </small>
                    </td>
                    {headings.map(([key]) => (
                      <td key={key}>
                        {key === "price_vs_market"
                          ? signedPct(a[key])
                          : key.endsWith("share")
                            ? pct(a[key])
                            : key === "value_score"
                              ? a[key].toFixed(1)
                              : number(a[key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="footnote">
            {rows.length} areas · Click a heading to sort. Activity share is
            relative to all selected transactions before the area sample
            threshold.
          </p>
        </>
      )}
    </div>
  );
}
