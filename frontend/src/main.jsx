import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import {
  ErrorCard,
  Filters,
  Loading,
  initialFilters,
  paramsFor,
  useAsync,
} from "./ui";
import {
  AreasPage,
  HomePage,
  MarketPage,
  OpportunitiesPage,
} from "./market-pages";
import {
  PerformancePage,
  PredictPage,
  RoiPage,
  initialRoi,
} from "./valuation-pages";
import "./styles.css";

const pages = [
  [
    "home",
    "Overview",
    "Dubai, in perspective.",
    "A broad view of recorded property activity, pricing and the shape of the market.",
  ],
  [
    "market",
    "Market",
    "Read the market.",
    "Follow transaction activity. Understand the price distribution. Find the context behind the numbers.",
  ],
  [
    "areas",
    "Areas",
    "Location makes the difference.",
    "Compare entry prices, activity and property mix across Dubai’s recorded areas.",
  ],
  [
    "predict",
    "Valuation",
    "Put a price in context.",
    "Estimate a property’s historical transaction value, compare similar sales and test an asking price.",
  ],
  [
    "roi",
    "ROI & future value",
    "See the whole investment.",
    "Connect your valuation to rental income, ownership costs and a future sale.",
  ],
  [
    "opportunities",
    "Discover",
    "Build a sharper shortlist.",
    "Explore the balance between accessible pricing and recorded market activity.",
  ],
  [
    "performance",
    "The model",
    "Know what’s behind the estimate.",
    "The evidence, assumptions and boundaries of our valuation models.",
  ],
];
function App() {
  const [page, setPage] = useState("home"),
    [filters, setFilters] = useState(initialFilters),
    [valuation, setValuation] = useState(null),
    [roiForm, setRoiForm] = useState(initialRoi);
  const options = useAsync(api.options, []),
    marketPage = ["market", "areas", "opportunities"].includes(page);
  const params = paramsFor(filters, options.data?.years),
    key = JSON.stringify(params);
  const home = useAsync(() => api.overview({}), [], page === "home");
  const overview = useAsync(
    () => api.overview(params),
    [key],
    page === "market" && !!options.data,
  );
  const areas = useAsync(
    () => api.areas(params),
    [key],
    ["market", "areas"].includes(page) && !!options.data,
  );
  const opportunities = useAsync(
    () => api.opportunities(params),
    [key],
    page === "opportunities" && !!options.data,
  );
  const navigate = (next) => {
    setPage(next);
    window.scrollTo({ top: 0, behavior: "instant" });
  };
  const useValuation = (value) =>
    setRoiForm((c) => ({
      ...c,
      purchase_price: Math.round(
        value.result.asking_price || value.result.predicted_price,
      ),
      model_value: value.result.predicted_price,
      use_model: true,
    }));
  const current = pages.find((item) => item[0] === page);
  const renderState = (state, render) =>
    state.loading ? (
      <Loading />
    ) : state.error ? (
      <ErrorCard error={state.error} />
    ) : state.data ? (
      render(state.data)
    ) : (
      <Loading />
    );
  return (
    <>
      <header className="site-header">
        <div className="brand">
          <span className="brand-mark">d.</span>
          <div>
            DUBAI<span>PROPERTY INTELLIGENCE</span>
          </div>
        </div>
        <span className="header-note">
          <span />
          Transaction research
        </span>
      </header>
      <nav className="top-nav" aria-label="Main navigation">
        {pages.map(([key, label]) => (
          <button
            key={key}
            aria-current={page === key ? "page" : undefined}
            className={page === key ? "active" : ""}
            onClick={() => navigate(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      <main>
        {page !== "home" && (
          <div className="page-heading">
            <span className="eyebrow">Dubai / {current[1]}</span>
            <h1>{current[2]}</h1>
            <p>{current[3]}</p>
          </div>
        )}
        {marketPage &&
          (options.data ? (
            <Filters
              options={options.data}
              value={filters}
              onApply={setFilters}
            />
          ) : options.error ? (
            <ErrorCard error={options.error} />
          ) : (
            <Loading />
          ))}
        {page === "home" &&
          renderState(home, (data) => (
            <HomePage data={data} navigate={navigate} />
          ))}
        {page === "market" &&
          renderState(overview, (data) =>
            renderState(areas, (areaData) => (
              <MarketPage data={data} areas={areaData} />
            )),
          )}
        {page === "areas" &&
          renderState(areas, (data) => <AreasPage areas={data} />)}
        {page === "predict" && (
          <PredictPage
            saved={valuation}
            onPrediction={setValuation}
            openRoi={(value) => {
              useValuation(value);
              navigate("roi");
            }}
          />
        )}
        {page === "roi" && (
          <RoiPage
            form={roiForm}
            setForm={setRoiForm}
            valuation={valuation}
            useValuation={useValuation}
            navigate={navigate}
          />
        )}
        {page === "opportunities" &&
          renderState(opportunities, (data) => (
            <OpportunitiesPage areas={data} />
          ))}
        {page === "performance" && <PerformancePage />}
        <footer>
          <span className="brand-word">d. / Dubai property intelligence</span>
          <p>
            Prepared sales data · Historical evidence, not live listings.
            <br />
            Valuations are estimates. Returns depend on your assumptions.
          </p>
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
