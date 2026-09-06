import React, { useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";
import { api } from "./api";
import {
  Chart,
  Empty,
  ErrorCard,
  Loading,
  Metric,
  Note,
  SectionHead,
  money,
  number,
  pct,
  signedPct,
  titleCase,
  useAsync,
} from "./ui";

const predictionFields = [
  ["area_name_en", "Area"],
  ["property_type_en", "Property type"],
  ["property_sub_type_en", "Subtype"],
  ["property_usage_en", "Usage"],
  ["rooms_en", "Rooms"],
  ["reg_type_en", "Registration"],
  ["procedure_name_en", "Procedure"],
];
export const initialRoi = {
  purchase_price: 1000000,
  monthly_rent: 7500,
  annual_costs: 15000,
  closing_cost_rate: 0.04,
  vacancy_rate: 0.05,
  appreciation_rate: 0.03,
  holding_years: 5,
  selling_cost_rate: 0.02,
};
export function PredictPage({ saved, onPrediction, openRoi }) {
  const [form, setForm] = useState(
    saved?.form ?? {
      area_name_en: "",
      property_type_en: "",
      property_sub_type_en: "",
      property_usage_en: "",
      rooms_en: "",
      reg_type_en: "",
      procedure_name_en: "",
      has_parking: true,
      procedure_area: 100,
      year: 2025,
      month: 12,
      asking_price: "",
    },
  );
  const [result, setResult] = useState(saved?.result ?? null),
    [error, setError] = useState(null),
    [busy, setBusy] = useState(false);
  const scopes = useMemo(
    () =>
      Object.fromEntries(
        predictionFields
          .filter(([key]) => form[key])
          .map(([key]) => [key, form[key]]),
      ),
    [form],
  );
  const optionState = useAsync(
      () => api.predictionOptions(scopes),
      [JSON.stringify(scopes)],
    ),
    options = optionState.data ?? {};
  const update = (key, value) => {
    setResult(null);
    setError(null);
    setForm((current) => {
      const next = { ...current, [key]: value },
        index = predictionFields.findIndex(([field]) => field === key);
      if (index >= 0)
        predictionFields.slice(index + 1).forEach(([field]) => {
          next[field] = "";
        });
      return next;
    });
  };
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const prediction = await api.predictPrice({
        ...form,
        asking_price: form.asking_price ? Number(form.asking_price) : null,
      });
      setResult(prediction);
      onPrediction({ form, result: prediction });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-grid">
      <div className="two-col">
        <Note title="Valuation answers: what is it worth?">
          The saved model estimates a registered transaction value for a
          property's attributes and reference date. Compare an asking price to
          that estimate to frame a buyer's offer or a seller's pricing
          discussion.
        </Note>
        <Note title="ROI answers: what could I earn?">
          Send the valuation to ROI to model rent, costs and an exit value.
          Future value starts from the estimate and compounds your growth
          assumption; the model does not independently forecast future
          appreciation.
        </Note>
      </div>
      <form className="panel" onSubmit={submit}>
        <SectionHead
          kicker="01 / Property profile"
          title="Build your valuation"
        />
        <p className="footnote">
          Choose fields from left to right. Choices follow combinations in the
          data that the model supports; changing an earlier field clears later
          selections.
        </p>
        <fieldset disabled={busy} className="predict-form">
          {predictionFields.map(([key, label]) => (
            <label key={key}>
              {label}
              <select
                required
                value={form[key]}
                disabled={optionState.loading}
                onChange={(e) => update(key, e.target.value)}
              >
                <option value="">Choose {label.toLowerCase()}</option>
                {(options[key] ?? (form[key] ? [form[key]] : [])).map(
                  (value) => (
                    <option key={value} value={value}>
                      {titleCase(value)}
                    </option>
                  ),
                )}
              </select>
            </label>
          ))}
          <label>
            Property size · sqm
            <input
              required
              type="number"
              min="1"
              step="any"
              value={form.procedure_area}
              onChange={(e) => update("procedure_area", Number(e.target.value))}
            />
          </label>
          <label>
            Reference year
            <select
              value={form.year}
              onChange={(e) => update("year", Number(e.target.value))}
            >
              {(options.years ?? [form.year]).map((year) => (
                <option key={year}>{year}</option>
              ))}
            </select>
          </label>
          <label>
            Reference month
            <select
              value={form.month}
              onChange={(e) => update("month", Number(e.target.value))}
            >
              {Array.from({ length: 12 }, (_, i) => (
                <option key={i + 1} value={i + 1}>
                  {new Date(2025, i, 1).toLocaleString("en", { month: "long" })}
                </option>
              ))}
            </select>
          </label>
          <label>
            Asking price · AED (optional)
            <input
              type="number"
              min="1"
              step="any"
              placeholder="Compare a seller’s price"
              value={form.asking_price}
              onChange={(e) => update("asking_price", e.target.value)}
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.has_parking}
              onChange={(e) => update("has_parking", e.target.checked)}
            />
            Parking included
          </label>
        </fieldset>
        {optionState.loading && (
          <p className="footnote" role="status">
            Loading supported property choices… The first model load can take a
            moment.
          </p>
        )}
        {optionState.error && <ErrorCard error={optionState.error} />}
        <div className="form-bottom">
          <p>
            Only model-supported categories are offered. Your entered property
            size stays under your control.
          </p>
          <button
            className="primary"
            disabled={busy || optionState.loading || !!optionState.error}
          >
            {busy ? "Estimating…" : "Estimate value"}
            <ArrowRight size={17} />
          </button>
        </div>
      </form>
      {error && <ErrorCard error={error} />}
      {result && (
        <>
          <div className="valuation-result">
            <div>
              <span className="eyebrow">
                Model estimate / {result.reference_date}
              </span>
              <strong>{money(result.predicted_price)}</strong>
              <p>
                {money(result.predicted_price_per_sqm)} per sqm ·{" "}
                {titleCase(form.area_name_en)}
              </p>
            </div>
            <button
              className="primary"
              onClick={() => openRoi({ form, result })}
            >
              Use in ROI & future value
              <ArrowRight size={17} />
            </button>
          </div>
          <div className="metrics-grid">
            <Metric
              label="Matched transactions"
              value={number(result.similar_count)}
              hint={
                result.similar_count < 10
                  ? "Limited evidence · price band withheld"
                  : "Similar historical records"
              }
            />
            <Metric
              label="Comparable median"
              value={money(result.similar_median_price)}
            />
            <Metric
              label="Estimate vs comparable median"
              value={signedPct(result.model_vs_comparables)}
            />
            <Metric
              label="Asking price vs model"
              value={signedPct(result.asking_vs_model)}
              hint="Positive = asking above model estimate"
            />
          </div>
          <div className="two-col">
            <Note title="Comparable price band">
              {result.similar_count >= 10
                ? `The middle half of matched transactions falls between ${money(result.similar_p25)} and ${money(result.similar_p75)}. This is an observed price spread, not a model confidence interval.`
                : "Fewer than ten matched records support this profile. A comparable median and price band are withheld to avoid overstating the evidence."}{" "}
              {result.comparable_scope}
            </Note>
            <Note title="Put the estimate in proportion">
              Historical test MAE is {money(result.historical_mae)} across the
              evaluation set. It is not a property-specific error bound. Views,
              condition, floor level and exact building quality are missing, so
              an asking-price gap alone does not establish a bargain.
            </Note>
          </div>
        </>
      )}
    </div>
  );
}
export function RoiPage({ form, setForm, valuation, useValuation, navigate }) {
  const useModel = form.use_model ?? !!form.model_value;
  const setUseModel = (value) =>
    setForm((current) => ({ ...current, use_model: value }));
  const { use_model, ...assumptions } = form;
  const payload = {
    ...assumptions,
    model_value: useModel ? form.model_value : null,
  };
  const valid =
    Object.entries(payload).every(
      ([key, value]) =>
        key === "model_value" ||
        (value !== "" && Number.isFinite(Number(value))),
    ) && form.purchase_price > 0;
  const state = useAsync(
    () => api.roi(payload),
    [JSON.stringify(payload)],
    valid,
  );
  const fields = [
    ["purchase_price", "Purchase price · AED", 1, undefined, false],
    ["monthly_rent", "Monthly rent · AED", 0, undefined, false],
    ["annual_costs", "Annual ownership costs · AED", 0, undefined, false],
    ["closing_cost_rate", "Purchase costs · %", 0, 20, true],
    ["vacancy_rate", "Vacancy allowance · %", 0, 50, true],
    ["appreciation_rate", "Annual value growth · %", -50, 50, true],
    ["holding_years", "Holding period · years", 1, 30, false],
    ["selling_cost_rate", "Selling costs · %", 0, 20, true],
  ];
  const result = state.data,
    exit = result?.projection.at(-1);
  return (
    <div className="page-grid">
      <div className="model-transfer">
        <div>
          <strong>
            {valuation
              ? `Saved valuation: ${money(valuation.result.predicted_price)}`
              : "Start with a model valuation or your own price"}
          </strong>
          <p>
            {valuation
              ? `${titleCase(valuation.form.area_name_en)} · Reference ${valuation.result.reference_date}`
              : "A valuation provides a separate starting value, while the purchase price remains what you expect to pay."}
          </p>
        </div>
        <button
          className="secondary"
          onClick={() => {
            if (valuation) {
              useValuation(valuation);
              setUseModel(true);
            } else navigate("predict");
          }}
        >
          {valuation ? "Apply saved valuation" : "Value a property"}
          <ArrowRight size={15} />
        </button>
      </div>
      <div className="panel">
        <SectionHead
          kicker="02 / Investment assumptions"
          title="Define your scenario"
        />
        <div className="predict-form">
          {fields.map(([key, label, min, max, percent]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                required
                min={min}
                max={max}
                step={key === "holding_years" ? 1 : "any"}
                value={
                  form[key] === ""
                    ? ""
                    : percent
                      ? Number((form[key] * 100).toFixed(6))
                      : form[key]
                }
                onChange={(e) =>
                  setForm((c) => ({
                    ...c,
                    [key]:
                      e.target.value === ""
                        ? ""
                        : Number(e.target.value) / (percent ? 100 : 1),
                  }))
                }
              />
            </label>
          ))}
        </div>
        {form.model_value && (
          <label className="checkbox-label baseline-toggle">
            <input
              type="checkbox"
              checked={useModel}
              onChange={(e) => setUseModel(e.target.checked)}
            />
            Start future value from the model estimate of{" "}
            {money(form.model_value)}
          </label>
        )}
        <p className="footnote">
          Cash purchase scenario. Rent and annual costs stay constant. Growth,
          vacancy and fees are editable assumptions, not inferred rental data or
          verified charges. Financing, taxes and reinvestment are excluded.
        </p>
      </div>
      {!valid && (
        <Empty>
          Enter complete numeric assumptions to calculate your scenario.
        </Empty>
      )}
      {valid && state.error && <ErrorCard error={state.error} />}
      {valid && state.loading && <Loading />}
      {valid && result && (
        <>
          <div className="metrics-grid">
            <Metric
              label="Net rental yield"
              value={pct(result.net_yield)}
              hint="Annual net rent / total acquisition cost"
            />
            <Metric
              label="Annual net income"
              value={money(result.annual_net_income)}
            />
            <Metric
              label={`Value after ${form.holding_years} years`}
              value={money(exit.future_value)}
              hint="Scenario value before sale costs"
            />
            <Metric
              label="Total holding-period return"
              value={pct(exit.total_roi)}
              hint="Includes rent, purchase and sale costs"
            />
          </div>
          <div className="two-col">
            <Chart
              data={result.projection}
              xKey="year"
              yKey="future_value"
              title="Future value · assumed growth"
              format={money}
            />
            <div className="panel cashflow">
              <h3>Your exit, explained</h3>
              {[
                ["Total acquisition cost", result.acquisition_cost],
                ["Cumulative net rental income", exit.rental_income],
                ["Sale proceeds after selling costs", exit.sale_proceeds],
                ["Net profit over holding period", exit.net_profit],
              ].map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{money(value)}</strong>
                </div>
              ))}
              <p>
                Net profit = sale proceeds + cumulative net rent − total
                acquisition cost. Returns are cumulative, not annualized.
              </p>
            </div>
          </div>
          <div className="panel table-panel">
            <h3>How much does growth change the outcome?</h3>
            <div className="scroll-table">
              <table>
                <thead>
                  <tr>
                    <th>Scenario</th>
                    <th>Annual growth</th>
                    <th>Future value</th>
                    <th>Net profit</th>
                    <th>Total return</th>
                  </tr>
                </thead>
                <tbody>
                  {result.scenarios.map((row) => (
                    <tr key={row.label}>
                      <td>{row.label}</td>
                      <td>{pct(row.growth_rate)}</td>
                      <td>{money(row.future_value)}</td>
                      <td>{money(row.net_profit)}</td>
                      <td>{pct(row.total_roi)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="footnote">
              Sensitivity uses your growth assumption ±3 percentage points,
              capped at −50% and +50%. These are scenarios, not forecast
              probabilities.
            </p>
          </div>
          <div className="two-col">
            <Note
              title={`Break-even rent: ${money(result.break_even_monthly_rent)} / month`}
            >
              Rent needed to cover annual operating costs after the vacancy
              allowance. It does not recover the purchase price or cover
              mortgage payments.
            </Note>
            <Note
              title={`Break-even exit: ${money(result.break_even_sale_price)}`}
            >
              Sale value needed to recover acquisition costs after cumulative
              rental income and selling costs over {form.holding_years} years.
              Future value starts at {money(result.value_baseline)}
              {useModel
                ? " from your model estimate"
                : " from your purchase price"}
              .
            </Note>
          </div>
        </>
      )}
    </div>
  );
}
const figureNotes = {
  price_actual_vs_predicted: [
    "How close are the estimates?",
    "Points near the diagonal represent accurate estimates. Wider dispersion at higher prices means expensive and unusual properties need closer review.",
  ],
  price_error_distribution: [
    "Where does the model miss?",
    "The tails show large errors hidden by a single average. A central peak does not mean every property is estimated reliably.",
  ],
  xgboost_training_validation_rmse: [
    "What the learning curve says",
    "Falling validation error shows learning on held-out records. A widening gap from training error would suggest overfitting. This curve is on the log-price scale, not AED.",
  ],
  xgboost_feature_importance: [
    "Which inputs does the model use?",
    "Importance describes the model globally. It does not explain the exact contribution to your property's prediction or establish a causal relationship.",
  ],
  rooms_confusion_matrix: [
    "How room categories are inferred",
    "The diagonal shows correct classifications. Common room categories have more evidence; rare categories are less dependable. Only sufficiently confident imputations are accepted during preparation.",
  ],
};
export function PerformancePage() {
  const state = useAsync(api.performance, []);
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorCard error={state.error} />;
  const p = state.data;
  return (
    <div className="page-grid">
      <div className="model-story">
        <span className="eyebrow">The valuation pipeline</span>
        <h2>
          Historical evidence.
          <br />
          An informed estimate.
        </h2>
        <p>
          Cleaned transaction records establish the market context. CatBoost
          fills selected missing room categories; XGBoost uses property
          attributes, location and date to estimate registered value. The price
          model learns on a logarithmic scale to handle the large spread in
          property prices, then converts its output back to AED.
        </p>
      </div>
      <div className="metrics-grid">
        <Metric
          label="Price MAE"
          value={money(p.price_model.mae)}
          hint="Average absolute test error"
        />
        <Metric
          label="Price RMSE"
          value={money(p.price_model.rmse)}
          hint="More sensitive to large mistakes"
        />
        <Metric
          label="Price R²"
          value={p.price_model.r2.toFixed(3)}
          hint="Fit to held-out price variation"
        />
        <Metric
          label="Room classification accuracy"
          value={pct(p.rooms_model.accuracy)}
          hint="Share of correctly classified rooms"
        />
      </div>
      <div className="insight-grid">
        <Note title="MAE is context, not a price interval">
          An average miss of about AED 241k helps you judge the scale of
          uncertainty. It does not imply your property is within that amount of
          its true value. No calibrated per-property confidence interval is
          available.
        </Note>
        <Note title="R² is not prediction accuracy">
          An R² of 0.889 describes explained variation in the test set. It does
          not mean each estimated price is 88.9% accurate, or that performance
          will carry forward into a new market.
        </Note>
        <Note title="Room accuracy hides uneven coverage">
          Macro F1 is {p.rooms_model.macro_f1.toFixed(3)}, compared with
          weighted F1 of {p.rooms_model.weighted_f1.toFixed(3)}. The gap
          indicates weaker performance across less common room categories.
        </Note>
      </div>
      <SectionHead
        kicker="Evaluation evidence"
        title="Read the results, not just the score"
      />
      <div className="image-grid">
        {Object.entries(figureNotes).map(([key, [title, description]]) => (
          <figure className="panel" key={key}>
            <h3>{title}</h3>
            <img
              loading="lazy"
              src={`${api.base}${p.figures[key]}`}
              alt={title}
            />
            <figcaption>{description}</figcaption>
          </figure>
        ))}
      </div>
      <div className="two-col">
        <Note title="What the model cannot see">
          View, floor level, condition, renovations and exact building quality
          are missing from these inputs. Similar records still differ in these
          ways. Use the model with comparable sales and property-specific
          knowledge.
        </Note>
        <Note title="Why future value is a scenario">
          The saved model is a transaction-value regressor, not a validated
          time-series forecast. Feeding in a future year does not establish a
          reliable growth prediction. ROI therefore combines a starting
          valuation with explicit growth and cash-flow assumptions.
        </Note>
      </div>
      <Note title="Validation provenance">
        These are saved notebook evaluation results, not a live model audit. The
        API has no versioned training-period metadata or verified time-based
        backtest. Review note.ipynb for the research process before interpreting
        the metrics as evidence of future performance.
      </Note>
    </div>
  );
}
