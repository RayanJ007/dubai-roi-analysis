import React, { useState } from "react";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import {
  AreaTable,
  Bars,
  Chart,
  Empty,
  MarketMap,
  Metric,
  Note,
  SectionHead,
  compact,
  money,
  number,
  pct,
  titleCase,
} from "./ui";

function MarketInsights({ data }) {
  const m = data.metrics;
  return (
    <div className="insight-grid">
      <Note title={`${pct(m.under_1m_share)} at AED 1m or below`}>
        The share of recorded transactions within this entry budget. It reflects
        the selected property mix, not the supply of homes currently for sale.
      </Note>
      <Note title={`${pct(m.top_5_share)} concentrated in five areas`}>
        The five busiest areas account for this share of transactions.{" "}
        {titleCase(m.leading_area)} leads recorded activity.
      </Note>
      <Note title="The middle of the market">
        Half of recorded transaction values sit between {money(m.price_p25)} and{" "}
        {money(m.price_p75)}. This is the 25th–75th percentile range.
      </Note>
    </div>
  );
}
export function HomePage({ data, navigate }) {
  if (!data.metrics.transactions) return <Empty />;
  const m = data.metrics;
  return (
    <div className="page-grid">
      <div className="overview-lead">
        <div>
          <span className="eyebrow">Dubai property / market brief</span>
          <h2>
            A city of markets.
            <br />
            <span>Find your perspective.</span>
          </h2>
          <p>
            Understand where capital moves, what buyers pay and how a property
            fits into the bigger picture.
          </p>
          <button className="primary" onClick={() => navigate("market")}>
            Explore the market
            <ArrowUpRight size={18} />
          </button>
        </div>
        <div className="lead-stat">
          <span>Recorded transaction value</span>
          <strong>AED {compact(m.total_value)}</strong>
          <p>
            Across the prepared dataset
            <br />
            {data.coverage?.start} — {data.coverage?.end}
          </p>
          <span className="data-stamp">Historical sales snapshot</span>
        </div>
      </div>
      <div className="metrics-grid">
        <Metric
          label="Typical transaction"
          value={money(m.median_price)}
          hint="Median registered value"
        />
        <Metric
          label="Price per square metre"
          value={money(m.median_price_per_sqm)}
          hint="Median across individual transactions"
        />
        <Metric
          label="Off-plan share"
          value={pct(m.off_plan_share)}
          hint="Share of recorded transactions"
        />
        <Metric
          label="Accessible entry point"
          value={pct(m.under_1m_share)}
          hint="Transactions at AED 1m or below"
        />
      </div>
      <SectionHead
        kicker="Beyond the headline"
        title="What the data tells us"
      />
      <MarketInsights data={data} />
      <div className="two-col">
        <Chart
          data={data.annual}
          xKey="year"
          yKey="transactions"
          title="Activity through the years"
        />
        <Bars
          data={data.property_mix}
          title="The property mix"
          labelKey="property_type_en"
        />
      </div>
      <div className="workflow">
        <div>
          <span className="eyebrow">From context to a decision</span>
          <h2>One property. A fuller picture.</h2>
          <p>
            Start with comparable market evidence, estimate value, then test the
            economics of holding and selling.
          </p>
        </div>
        <button onClick={() => navigate("predict")}>
          01<strong>Estimate a value</strong>
          <ArrowRight size={20} />
        </button>
        <button onClick={() => navigate("roi")}>
          02<strong>Test your return</strong>
          <ArrowRight size={20} />
        </button>
      </div>
      <Note title="How to read this overview">
        This unfiltered view covers registered sales in the prepared Dubai
        dataset, excluding mortgages and gifts. Medians describe a changing mix
        of properties, so a rise in the median is not the same as appreciation
        of an identical home. Dates reflect the saved source, including any
        future-dated records; this is not a live market feed.
      </Note>
    </div>
  );
}
export function MarketPage({ data, areas }) {
  const [frequency, setFrequency] = useState("monthly");
  if (!data.metrics.transactions) return <Empty />;
  const m = data.metrics,
    series = frequency === "monthly" ? data.monthly : data.annual,
    xKey = frequency === "monthly" ? "month_start" : "year";
  return (
    <div className="page-grid">
      <div className="metrics-grid">
        <Metric label="Recorded transactions" value={number(m.transactions)} />
        <Metric
          label="Total transaction value"
          value={`AED ${compact(m.total_value)}`}
        />
        <Metric label="Median transaction" value={money(m.median_price)} />
        <Metric
          label="Median price / sqm"
          value={money(m.median_price_per_sqm)}
        />
      </div>
      <SectionHead kicker="Market movement" title="Activity and pricing">
        <div className="segmented">
          {["monthly", "annual"].map((item) => (
            <button
              key={item}
              className={frequency === item ? "active" : ""}
              onClick={() => setFrequency(item)}
            >
              {titleCase(item)}
            </button>
          ))}
        </div>
      </SectionHead>
      <div className="two-col">
        <Chart
          data={series}
          xKey={xKey}
          yKey="transactions"
          title="Transaction volume"
        />
        <Chart
          data={series}
          xKey={xKey}
          yKey="median_price"
          title="Median transaction price"
          format={money}
          color="#e9b578"
        />
      </div>
      <p className="footnote">
        Months without records are omitted. Partial periods and changes in
        property mix can distort comparisons. Hover for values or open a chart’s
        data table.
      </p>
      <MarketInsights data={data} />
      <div className="two-col">
        <Bars
          data={data.price_bands}
          title="Where buyers transact"
          labelKey="label"
        />
        <Bars
          data={data.property_mix}
          title="Activity by property type"
          labelKey="property_type_en"
        />
      </div>
      <MarketMap areas={areas} />
      <Bars data={areas} title="Most active qualifying areas" />
      <Note title="Price per square metre adds context">
        Dividing each transaction’s value by its recorded size makes
        different-sized properties easier to compare. It still reflects
        location, type and registration mix. Off-plan transactions account for{" "}
        {pct(m.off_plan_share)} of the current selection.
      </Note>
    </div>
  );
}
export function AreasPage({ areas }) {
  const affordable = [...areas].sort(
    (a, b) => a.median_price_per_sqm - b.median_price_per_sqm,
  )[0];
  return (
    <div className="page-grid">
      <div className="insight-grid">
        <Note title="Activity is one part of liquidity">
          More recorded transactions mean more market evidence. Counts alone do
          not tell you how quickly a particular property will sell.
        </Note>
        <Note
          title={
            affordable ? titleCase(affordable.area_name_en) : "Entry pricing"
          }
        >
          {affordable
            ? `The lowest median price per sqm among qualifying areas: ${money(affordable.median_price_per_sqm)}. Compare the property mix before treating this as a discount.`
            : "Select a broader range to compare areas."}
        </Note>
        <Note title="Read the price spread">
          The middle 50% of transaction values gives a sense of the area's price
          range. A wide range may signal several very different property
          segments.
        </Note>
      </div>
      <div className="two-col">
        <Bars data={areas} title="Activity leaders" />
        <Bars
          data={[...areas].sort(
            (a, b) => a.median_price_per_sqm - b.median_price_per_sqm,
          )}
          title="Lower entry prices / sqm"
          valueKey="median_price_per_sqm"
          format={money}
        />
      </div>
      <AreaTable areas={areas} />
      <MarketMap areas={areas} />
    </div>
  );
}
export function OpportunitiesPage({ areas }) {
  return (
    <div className="page-grid">
      <div className="insight-grid">
        <Note title="An explainable screening score">
          A score out of 100 equally weights activity percentile and
          affordability percentile among qualifying areas. Lower median AED/sqm
          and higher transaction counts rank higher.
        </Note>
        <Note title="A relative shortlist">
          The score changes with your filters and minimum sample size. It does
          not estimate future returns, identify undervalued listings or account
          for rent, condition and ownership costs.
        </Note>
        <Note title="Look at the mix">
          Use off-plan share and the typical price band to check whether an area
          matches your intended purchase. Compare a specific property in
          Valuation before building an ROI scenario.
        </Note>
      </div>
      <Bars
        data={areas}
        title="Activity meets affordability"
        valueKey="value_score"
        format={(v) => `${v.toFixed(1)} / 100`}
      />
      <AreaTable areas={areas} discover />
    </div>
  );
}
