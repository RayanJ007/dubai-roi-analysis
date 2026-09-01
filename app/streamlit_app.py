from __future__ import annotations

import calendar
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from note import (  # noqa: E402
    align_price_categories,
    calculate_roi,
    filter_price_model_domain,
    get_price_model_categories,
    load_area_coordinates,
    load_price_model,
    make_prediction_row,
    predict_prices,
    prepare_dashboard_data,
    prepare_price_features,
)

MONTH_OPTIONS = {calendar.month_name[number]: number for number in range(1, 13)}


st.set_page_config(
    page_title="Dubai Real Estate Dashboard",
    page_icon="Dubai",
    layout="wide",
)


@st.cache_data(show_spinner="Loading dashboard data...")
def get_data() -> pd.DataFrame:
    return prepare_dashboard_data()


@st.cache_data
def get_area_coordinates() -> pd.DataFrame:
    return load_area_coordinates()


@st.cache_resource(show_spinner="Loading price model...")
def get_price_model():
    return load_price_model()


@st.cache_data(show_spinner="Reading saved model categories...")
def get_saved_price_categories() -> dict[str, list[str]]:
    return get_price_model_categories(load_price_model())


@st.cache_data(show_spinner="Preparing prediction options...")
def get_prediction_data() -> pd.DataFrame:
    data = prediction_domain(get_data())
    category_values = get_saved_price_categories()

    for column, values in category_values.items():
        if column in data.columns:
            data = data[data[column].astype(str).isin(values)]

    return data.copy()


def prepare_prediction_features(row: pd.DataFrame) -> pd.DataFrame:
    prepared = prepare_price_features(row)
    return align_price_categories(prepared, get_saved_price_categories())


def option_count(data: pd.DataFrame, column: str) -> int:
    if column not in data.columns:
        return 0
    return data[column].dropna().astype(str).nunique()


def restrict_scoped_data(data: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    filtered = data[data[column].astype(str).eq(str(value))]
    return filtered if not filtered.empty else data


def select_from_scope(label: str, data: pd.DataFrame, column: str, default: str | None = None) -> str:
    return safe_selectbox(label, get_options(data, column), default=default)


def money(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    return f"AED {value:,.0f}"


def pct(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{100 * value:.2f}%"


def get_options(data: pd.DataFrame, column: str) -> list[str]:
    if column not in data.columns:
        return []
    return (
        data[column]
        .dropna()
        .astype(str)
        .sort_values()
        .unique()
        .tolist()
    )


def safe_selectbox(label: str, options: list[str], default: str | None = None) -> str:
    if not options:
        st.warning(f"No available options for {label}.")
        return ""
    index = options.index(default) if default in options else 0
    return st.selectbox(label, options, index=index)


def prediction_domain(data: pd.DataFrame) -> pd.DataFrame:
    domain = filter_price_model_domain(data)
    domain = domain.dropna(subset=["rooms_en", "actual_worth", "procedure_area"]).copy()
    domain = domain[domain["procedure_area"].gt(0)]
    return domain


def area_summary(data: pd.DataFrame) -> pd.DataFrame:
    return (
        data
        .dropna(subset=["area_name_en", "actual_worth", "procedure_area"])
        .assign(price_per_sqm=lambda df: df["actual_worth"] / df["procedure_area"])
        .groupby("area_name_en", observed=True)
        .agg(
            transactions=("actual_worth", "size"),
            median_price=("actual_worth", "median"),
            mean_price=("actual_worth", "mean"),
            median_price_per_sqm=("price_per_sqm", "median"),
            median_area=("procedure_area", "median"),
        )
        .reset_index()
        .sort_values("transactions", ascending=False)
    )


def area_summary_with_coordinates(data: pd.DataFrame) -> pd.DataFrame:
    summary = area_summary(data)
    coordinates = get_area_coordinates()
    return summary.merge(coordinates, on="area_name_en", how="left")


def area_map(summary: pd.DataFrame, title: str, key: str) -> None:
    mapped = summary.dropna(subset=["latitude", "longitude"]).copy()
    if mapped.empty:
        st.info("Map coordinates are not available for the selected areas yet.")
        return

    mapped["display_area"] = mapped["area_name_en"].astype(str).str.title()

    all_areas_option = "All mapped areas"
    area_options = [all_areas_option] + mapped["area_name_en"].astype(str).sort_values().tolist()
    selected_area = st.selectbox(
        "Search map area",
        area_options,
        key=f"{key}_area_search",
        help="Click and type to search for a Dubai area.",
        format_func=lambda value: all_areas_option if value == all_areas_option else value.title(),
    )

    if selected_area == all_areas_option:
        center = {"lat": 25.12, "lon": 55.25}
        zoom = 9
    else:
        selected_row = mapped[mapped["area_name_en"].astype(str).eq(selected_area)].iloc[0]
        center = {"lat": selected_row["latitude"], "lon": selected_row["longitude"]}
        zoom = 12

    st.plotly_chart(
        px.scatter_mapbox(
            mapped,
            lat="latitude",
            lon="longitude",
            size="transactions",
            color="median_price_per_sqm",
            hover_name="display_area",
            hover_data={
                "area_name_en": False,
                "display_area": False,
                "transactions": ":,",
                "median_price": ":,.0f",
                "median_price_per_sqm": ":,.0f",
                "latitude": False,
                "longitude": False,
            },
            color_continuous_scale="Viridis",
            center=center,
            zoom=zoom,
            height=520,
            title=title,
        ).update_layout(mapbox_style="carto-positron", margin=dict(l=0, r=0, t=45, b=0)),
        use_container_width=True,
    )


def sidebar_filters(data: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    years = sorted(data["year"].dropna().astype(int).unique().tolist())
    selected_years = st.sidebar.multiselect(
        "Year",
        years,
        default=years[-5:] if len(years) > 5 else years,
    )

    property_types = get_options(data, "property_type_en")
    selected_property_types = st.sidebar.multiselect(
        "Property type",
        property_types,
        default=property_types,
    )

    areas = get_options(data, "area_name_en")
    selected_areas = st.sidebar.multiselect(
        "Area",
        areas,
        default=[],
        help="Leave empty to include all areas.",
    )

    filtered = data.copy()
    if selected_years:
        filtered = filtered[filtered["year"].isin(selected_years)]
    if selected_property_types:
        filtered = filtered[filtered["property_type_en"].astype(str).isin(selected_property_types)]
    if selected_areas:
        filtered = filtered[filtered["area_name_en"].astype(str).isin(selected_areas)]

    return filtered


def market_overview(data: pd.DataFrame) -> None:
    st.header("Market Overview")

    total_transactions = len(data)
    median_price = data["actual_worth"].median()
    median_area = data["procedure_area"].median()
    median_ppsqm = (data["actual_worth"] / data["procedure_area"]).median()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", f"{total_transactions:,}")
    c2.metric("Median Price", money(median_price))
    c3.metric("Median Area", f"{median_area:,.0f} sqm")
    c4.metric("Median Price / sqm", money(median_ppsqm))

    monthly = (
        data
        .dropna(subset=["instance_date", "actual_worth"])
        .assign(month_start=lambda df: df["instance_date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month_start", observed=True)
        .agg(transactions=("actual_worth", "size"), median_price=("actual_worth", "median"))
        .reset_index()
    )

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            px.line(monthly, x="month_start", y="transactions", title="Transaction Volume Over Time"),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            px.line(monthly, x="month_start", y="median_price", title="Median Price Over Time"),
            use_container_width=True,
        )

    top_areas = area_summary(data).head(15)
    st.plotly_chart(
        px.bar(
            top_areas.sort_values("transactions"),
            x="transactions",
            y="area_name_en",
            orientation="h",
            title="Top Areas By Transaction Count",
        ),
        use_container_width=True,
    )

    area_map(
        area_summary_with_coordinates(data).head(60),
        "Dubai Area Activity And Median Price Per Sqm",
        key="market_overview_map",
    )


def area_comparison(data: pd.DataFrame) -> None:
    st.header("Area Comparison")

    summary = area_summary(data)
    min_transactions = st.slider("Minimum transactions", 25, 1000, 100, step=25)
    summary = summary[summary["transactions"] >= min_transactions]

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            px.bar(
                summary.head(20).sort_values("median_price"),
                x="median_price",
                y="area_name_en",
                orientation="h",
                title="Top 20 Active Areas By Median Price",
            ),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            px.scatter(
                summary,
                x="median_area",
                y="median_price",
                size="transactions",
                hover_name="area_name_en",
                title="Median Area Vs Median Price",
            ),
            use_container_width=True,
        )

    area_map(
        summary.head(80).merge(get_area_coordinates(), on="area_name_en", how="left"),
        "Selected Areas On Map",
        key="area_comparison_map",
    )

    st.dataframe(summary, use_container_width=True, hide_index=True)


def price_prediction(data: pd.DataFrame) -> float | None:
    st.header("Price Prediction")

    try:
        model = get_price_model()
    except Exception as exc:
        st.error(f"Could not load the price model: {exc}")
        return None

    model_data = get_prediction_data()
    if model_data.empty:
        st.error("No residential sales records are available for price prediction.")
        return None

    st.caption("Prediction inputs are limited to residential sales categories stored in the saved model.")

    c1, c2, c3 = st.columns(3)

    with c1:
        area_name = select_from_scope("Area", model_data, "area_name_en")
        scoped = restrict_scoped_data(model_data, "area_name_en", area_name)

        property_sub_type = select_from_scope(
            "Property subtype",
            scoped,
            "property_sub_type_en",
            default="flat",
        )
        scoped = restrict_scoped_data(scoped, "property_sub_type_en", property_sub_type)

        property_type = select_from_scope("Property type", scoped, "property_type_en")
        scoped = restrict_scoped_data(scoped, "property_type_en", property_type)

        property_usage = select_from_scope("Property usage", scoped, "property_usage_en")
        scoped = restrict_scoped_data(scoped, "property_usage_en", property_usage)

    with c2:
        rooms = select_from_scope("Rooms", scoped, "rooms_en")
        scoped = restrict_scoped_data(scoped, "rooms_en", rooms)

        reg_type = select_from_scope("Registration type", scoped, "reg_type_en")
        scoped = restrict_scoped_data(scoped, "reg_type_en", reg_type)

        procedure_name = select_from_scope("Procedure", scoped, "procedure_name_en")
        scoped = restrict_scoped_data(scoped, "procedure_name_en", procedure_name)

        advertised_area = select_from_scope("Advertised area", scoped, "advertised_area")

    with c3:
        median_area = float(scoped["procedure_area"].median()) if not scoped.empty else 100.0
        procedure_area = st.number_input(
            "Property area (sqm)",
            min_value=1.0,
            value=max(1.0, median_area),
            step=5.0,
        )
        has_parking = st.toggle("Has parking", value=True)
        year = st.number_input("Year", min_value=2000, max_value=2035, value=2026, step=1)
        month_name = st.selectbox("Month", list(MONTH_OPTIONS), index=0)
        month = MONTH_OPTIONS[month_name]

    if not st.button("Predict price", type="primary"):
        return None

    row = make_prediction_row(
        procedure_name_en=procedure_name,
        property_type_en=property_type,
        property_sub_type_en=property_sub_type,
        property_usage_en=property_usage,
        reg_type_en=reg_type,
        area_name_en=area_name,
        rooms_en=rooms,
        has_parking=has_parking,
        procedure_area=procedure_area,
        advertised_area=advertised_area,
        year=int(year),
        month=int(month),
    )

    try:
        prepared = prepare_prediction_features(row)
        predicted_price = float(predict_prices(model, prepared)[0])
    except Exception as exc:
        st.error(
            "This exact input could not be predicted with the saved XGBoost model. "
            f"Details: {exc}"
        )
        return None

    predicted_ppsqm = predicted_price / procedure_area

    c1, c2 = st.columns(2)
    c1.metric("Predicted Price", money(predicted_price))
    c2.metric("Predicted Price / sqm", money(predicted_ppsqm))

    similar = model_data[
        model_data["area_name_en"].astype(str).eq(str(area_name))
        & model_data["property_type_en"].astype(str).eq(str(property_type))
        & model_data["rooms_en"].astype(str).eq(str(rooms))
    ]

    if len(similar) >= 10:
        median_similar = similar["actual_worth"].median()
        difference = predicted_price - median_similar
        st.info(
            f"Similar-property median: {money(median_similar)}. "
            f"Prediction difference: {money(difference)}."
        )

    return predicted_price


def roi_calculator(default_price: float | None) -> None:
    st.header("ROI Calculator")

    c1, c2, c3 = st.columns(3)
    with c1:
        purchase_price = st.number_input(
            "Purchase price",
            min_value=1.0,
            value=float(default_price or 1_000_000),
            step=25_000.0,
        )
        monthly_rent = st.number_input("Expected monthly rent", min_value=0.0, value=7_500.0, step=250.0)

    with c2:
        annual_costs = st.number_input("Annual costs", min_value=0.0, value=15_000.0, step=1_000.0)
        closing_cost_rate = st.slider("Closing cost rate", 0.0, 0.10, 0.04, step=0.005)

    with c3:
        vacancy_rate = st.slider("Vacancy rate", 0.0, 0.30, 0.05, step=0.01)
        appreciation_rate = st.slider("Annual appreciation", -0.10, 0.20, 0.03, step=0.01)

    roi = calculate_roi(
        purchase_price=purchase_price,
        monthly_rent=monthly_rent,
        annual_costs=annual_costs,
        closing_cost_rate=closing_cost_rate,
        vacancy_rate=vacancy_rate,
        appreciation_rate=appreciation_rate,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gross Yield", pct(roi["gross_yield"]))
    c2.metric("Net Yield", pct(roi["net_yield"]))
    c3.metric("Annual Net Income", money(roi["annual_net_income"]))
    c4.metric("One-Year ROI", pct(roi["one_year_roi"]))

    st.dataframe(pd.DataFrame([roi]).T.rename(columns={0: "value"}), use_container_width=True)


def investment_opportunities(data: pd.DataFrame) -> None:
    st.header("Investment Opportunities")

    summary = area_summary(data)
    summary = summary[summary["transactions"] >= 100].copy()
    summary["value_score"] = (
        summary["transactions"].rank(pct=True)
        + summary["median_price_per_sqm"].rank(pct=True, ascending=False)
    )

    st.caption("Simple opportunity score: high transaction activity plus lower median price per sqm.")
    st.dataframe(
        summary.sort_values("value_score", ascending=False).head(25),
        use_container_width=True,
        hide_index=True,
    )

    st.plotly_chart(
        px.scatter(
            summary,
            x="median_price_per_sqm",
            y="transactions",
            size="median_area",
            hover_name="area_name_en",
            title="Activity Vs Median Price Per Sqm",
        ),
        use_container_width=True,
    )


def model_performance() -> None:
    st.header("Model Performance")

    figure_path = PROJECT_ROOT / "figures" / "xgboost_training_validation_rmse.png"
    if figure_path.exists():
        st.image(str(figure_path), caption="XGBoost training vs validation RMSE")
    else:
        st.warning("Training curve image not found.")

    st.markdown(
        """
        The price model predicts `log_actual_worth` and converts predictions back into AED.
        MAE and RMSE should be used to understand practical prediction error before using
        results in ROI decisions.

        The saved model is loaded from `models/xgboost_price_model.json`, so the dashboard
        can run predictions without retraining.
        """
    )


def main() -> None:
    st.title("Dubai Real Estate Dashboard")
    st.caption("Market analytics, price prediction, and ROI planning from Dubai transaction data.")

    try:
        data = get_data()
    except Exception as exc:
        st.error(f"Could not load dashboard data: {exc}")
        st.stop()

    filtered_data = sidebar_filters(data)

    page = st.sidebar.radio(
        "Dashboard",
        [
            "Market Overview",
            "Area Comparison",
            "Price Prediction",
            "ROI Calculator",
            "Investment Opportunities",
            "Model Performance",
        ],
    )

    predicted_price = None
    if page == "Market Overview":
        market_overview(filtered_data)
    elif page == "Area Comparison":
        area_comparison(filtered_data)
    elif page == "Price Prediction":
        predicted_price = price_prediction(data)
    elif page == "ROI Calculator":
        roi_calculator(default_price=None)
    elif page == "Investment Opportunities":
        investment_opportunities(filtered_data)
    elif page == "Model Performance":
        model_performance()

    if predicted_price is not None:
        with st.expander("Use this prediction in ROI calculator"):
            roi_calculator(default_price=predicted_price)


if __name__ == "__main__":
    main()
