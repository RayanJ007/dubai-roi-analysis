from __future__ import annotations

import calendar
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.io as pio
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from note import (  # noqa: E402
    DASHBOARD_CACHE_PATH,
    DASHBOARD_DB_PATH,
    DATA_DIR,
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
PAGES = [
    "Home",
    "Market Overview",
    "Area Comparison",
    "Price Prediction",
    "ROI Calculator",
    "Investment Opportunities",
    "Model Performance",
]


def get_secret(name: str, default: str | None = None) -> str | None:
    """Read a deployment setting from Streamlit secrets or environment variables."""

    value = os.getenv(name)
    if value:
        return value

    try:
        value = st.secrets[name]
    except (KeyError, FileNotFoundError):
        return default

    return str(value) if value else default


def download_file(url: str, destination: Path, token: str | None = None) -> None:
    """Download a private dashboard artifact into the local deployment filesystem."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url)

    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with tempfile.NamedTemporaryFile(delete=False, dir=destination.parent) as temp_file:
        temp_path = Path(temp_file.name)
        with urllib.request.urlopen(request, timeout=180) as response:
            shutil.copyfileobj(response, temp_file)

    temp_path.replace(destination)


def sqlite_years(path: Path) -> list[int]:
    """Read available transaction years from a dashboard SQLite file."""

    if not path.exists():
        return []

    try:
        with sqlite3.connect(path) as connection:
            rows = pd.read_sql_query(
                "SELECT DISTINCT year FROM transactions WHERE year IS NOT NULL ORDER BY year",
                connection,
            )
    except sqlite3.Error:
        return []

    return rows["year"].dropna().astype(int).tolist()


def has_historical_sqlite(path: Path) -> bool:
    """Return True when the SQLite data contains more than the 2026 update file."""

    years = sqlite_years(path)
    return len(years) > 1 or any(year < 2026 for year in years)


def ensure_remote_dashboard_storage() -> None:
    """Fetch deploy-only dashboard data when GitHub does not include the heavy files."""

    token = get_secret("DASHBOARD_DATA_TOKEN")
    db_url = get_secret("DASHBOARD_DB_URL")
    cache_url = get_secret("DASHBOARD_CACHE_URL")

    if db_url:
        if not has_historical_sqlite(DASHBOARD_DB_PATH):
            with st.spinner("Downloading prepared dashboard database..."):
                download_file(db_url, DASHBOARD_DB_PATH, token=token)

        if DASHBOARD_CACHE_PATH.exists():
            DASHBOARD_CACHE_PATH.unlink()
        return

    if DASHBOARD_CACHE_PATH.exists() or DASHBOARD_DB_PATH.exists():
        return

    if cache_url:
        with st.spinner("Downloading prepared dashboard cache..."):
            download_file(cache_url, DASHBOARD_CACHE_PATH, token=token)


st.set_page_config(
    page_title="Dubai Real Estate Dashboard",
    page_icon="DXB",
    layout="wide",
    initial_sidebar_state="collapsed",
)

pio.templates.default = "plotly_dark"


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --dxb-blue: #48a6ff;
            --dxb-orange: #ff8a2a;
            --dxb-ink: #f7fbff;
            --dxb-muted: #a9b4c5;
            --dxb-soft: #151a24;
            --dxb-line: #293244;
            --dxb-panel: #10151f;
            --dxb-panel-2: #171d29;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(72, 166, 255, 0.18), transparent 28rem),
                radial-gradient(circle at top right, rgba(255, 138, 42, 0.13), transparent 26rem),
                linear-gradient(180deg, #070a10 0%, #0b1018 54%, #080b11 100%);
            color: var(--dxb-ink);
        }

        h1, h2, h3, h4, h5, h6, p, li, label, span {
            color: inherit;
        }

        div[data-testid="stSidebar"] {
            display: none;
        }

        .block-container {
            max-width: 1220px;
            padding-top: 1.2rem;
            padding-bottom: 3rem;
        }

        .dxb-shell {
            border: 1px solid rgba(72, 166, 255, 0.18);
            border-radius: 22px;
            background: rgba(16, 21, 31, 0.86);
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.24);
            padding: 1rem 1.2rem;
            margin-bottom: 1rem;
        }

        .dxb-hero {
            border: 1px solid rgba(72, 166, 255, 0.20);
            border-radius: 28px;
            padding: 2.2rem;
            margin: 0.7rem 0 1.2rem;
            background:
                linear-gradient(135deg, rgba(72, 166, 255, 0.18), rgba(255, 138, 42, 0.12)),
                var(--dxb-panel);
            box-shadow: 0 22px 55px rgba(0, 0, 0, 0.32);
        }

        .dxb-kicker {
            color: var(--dxb-blue);
            font-weight: 800;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 0.4rem;
        }

        .dxb-hero h1 {
            font-size: 3rem;
            line-height: 1.02;
            margin: 0 0 0.7rem;
        }

        .dxb-hero p {
            max-width: 760px;
            color: var(--dxb-muted);
            font-size: 1.05rem;
            margin-bottom: 0;
        }

        .dxb-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1.2rem;
        }

        .dxb-pill {
            border: 1px solid var(--dxb-line);
            border-radius: 999px;
            padding: 0.45rem 0.75rem;
            background: rgba(255, 255, 255, 0.07);
            font-weight: 650;
            color: var(--dxb-ink);
        }

        .dxb-note {
            border-left: 5px solid var(--dxb-orange);
            border-radius: 12px;
            background: rgba(255, 138, 42, 0.13);
            color: #ffe4cc;
            padding: 0.9rem 1rem;
            margin: 1rem 0;
        }

        .dxb-definition {
            border: 1px solid rgba(72, 166, 255, 0.22);
            border-radius: 14px;
            background: rgba(72, 166, 255, 0.08);
            padding: 0.85rem 1rem;
            color: #d9e8ff;
            margin: 0.8rem 0;
        }

        div[data-testid="stMetric"] {
            background: var(--dxb-panel);
            border: 1px solid var(--dxb-line);
            border-radius: 18px;
            padding: 1rem;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.18);
        }

        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] div {
            color: var(--dxb-ink) !important;
        }

        .stRadio [role="radiogroup"] {
            display: flex;
            gap: 0.35rem;
            flex-wrap: wrap;
            border: 1px solid var(--dxb-line);
            border-radius: 999px;
            padding: 0.35rem;
            background: rgba(16, 21, 31, 0.88);
            box-shadow: 0 8px 22px rgba(0, 0, 0, 0.18);
        }

        .stRadio label {
            border-radius: 999px;
            padding: 0.35rem 0.65rem;
        }

        div[data-testid="stExpander"] {
            border-radius: 16px;
            border-color: var(--dxb-line);
            background: var(--dxb-panel);
        }

        div[data-testid="stDataFrame"],
        div[data-testid="stPlotlyChart"] {
            border: 1px solid var(--dxb-line);
            border-radius: 18px;
            overflow: hidden;
            background: var(--dxb-panel);
        }

        .stSelectbox div,
        .stMultiSelect div,
        .stNumberInput div,
        .stSlider div {
            color: var(--dxb-ink);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner="Loading dashboard data...")
def get_data() -> pd.DataFrame:
    ensure_remote_dashboard_storage()

    if DASHBOARD_DB_PATH.exists():
        with sqlite3.connect(DASHBOARD_DB_PATH) as connection:
            loaded = pd.read_sql_query(
                """
                SELECT
                    instance_date,
                    property_type_en,
                    area_name_en,
                    procedure_area,
                    actual_worth,
                    year,
                    month
                FROM transactions
                WHERE actual_worth IS NOT NULL
                  AND actual_worth > 0
                  AND procedure_area IS NOT NULL
                  AND procedure_area > 0
                """,
                connection,
                parse_dates=["instance_date"],
            )
    else:
        loaded = prepare_dashboard_data()

    years = sorted(loaded["year"].dropna().astype(int).unique().tolist())
    historical_csv_missing = not (DATA_DIR / "Transactions.csv").exists()
    remote_db_missing = not get_secret("DASHBOARD_DB_URL")

    if years == [2026] and historical_csv_missing and remote_db_missing:
        st.error(
            "Only the 2026 update file is available on this deployment. "
            "Add DASHBOARD_DB_URL in Streamlit secrets so the app can download "
            "the full historical dashboard.sqlite database."
        )
        st.stop()

    return loaded


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
    ensure_remote_dashboard_storage()

    if DASHBOARD_DB_PATH.exists():
        with sqlite3.connect(DASHBOARD_DB_PATH) as connection:
            data = pd.read_sql_query(
                """
                SELECT
                    trans_group_en,
                    procedure_name_en,
                    property_type_en,
                    property_sub_type_en,
                    property_usage_en,
                    reg_type_en,
                    area_name_en,
                    rooms_en,
                    has_parking,
                    procedure_area,
                    actual_worth,
                    advertised_area,
                    year,
                    month
                FROM transactions
                WHERE trans_group_en = 'sales'
                  AND rooms_en IS NOT NULL
                  AND actual_worth IS NOT NULL
                  AND actual_worth > 0
                  AND procedure_area IS NOT NULL
                  AND procedure_area > 0
                """,
                connection,
            )
    else:
        data = get_data()

    data = prediction_domain(data)
    category_values = get_saved_price_categories()

    for column, values in category_values.items():
        if column in data.columns:
            data = data[data[column].astype(str).isin(values)]

    return data.copy()


def prepare_prediction_features(row: pd.DataFrame) -> pd.DataFrame:
    prepared = prepare_price_features(row)
    return align_price_categories(prepared, get_saved_price_categories())


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


def format_title(value: str) -> str:
    return str(value).replace("_", " ").title()


def safe_selectbox(label: str, options: list[str], default: str | None = None) -> str:
    if not options:
        st.warning(f"No available options for {label}.")
        return ""
    index = options.index(default) if default in options else 0
    return st.selectbox(
        label,
        options,
        index=index,
        format_func=format_title,
    )


def restrict_scoped_data(data: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    filtered = data[data[column].astype(str).eq(str(value))]
    return filtered if not filtered.empty else data


def select_from_scope(label: str, data: pd.DataFrame, column: str, default: str | None = None) -> str:
    return safe_selectbox(label, get_options(data, column), default=default)


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


def disclaimer(kind: str = "general") -> None:
    if kind == "prediction":
        text = (
            "Model predictions are estimates from historical transaction patterns. They do not include "
            "unit condition, floor level, view, exact building quality, negotiation context, financing terms, "
            "or live market sentiment."
        )
    elif kind == "roi":
        text = (
            "ROI outputs are scenario calculations, not guaranteed returns. Results depend heavily on rent, "
            "vacancy, fees, maintenance, closing costs, financing, and resale assumptions."
        )
    else:
        text = (
            "This dashboard is for research and educational analysis only. It is not financial, legal, "
            "tax, or investment advice."
        )

    st.markdown(f"<div class='dxb-note'><strong>Disclaimer:</strong> {text}</div>", unsafe_allow_html=True)


def definition(title: str, body: str) -> None:
    st.markdown(
        f"<div class='dxb-definition'><strong>{title}</strong><br>{body}</div>",
        unsafe_allow_html=True,
    )


def header() -> str:
    st.markdown(
        """
        <div class="dxb-hero">
            <div class="dxb-kicker">Dubai transaction intelligence</div>
            <h1>Dubai Real Estate Dashboard</h1>
            <p>
                Explore market activity, compare areas, estimate property value, and test ROI scenarios
                using cleaned Dubai transaction data and saved machine-learning models.
            </p>
            <div class="dxb-pill-row">
                <span class="dxb-pill">Market analytics</span>
                <span class="dxb-pill">Area comparison</span>
                <span class="dxb-pill">Price prediction</span>
                <span class="dxb-pill">ROI scenarios</span>
                <span class="dxb-pill">Model evidence</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    return st.radio(
        "Dashboard section",
        PAGES,
        horizontal=True,
        label_visibility="collapsed",
    )


def top_filters(data: pd.DataFrame) -> pd.DataFrame:
    with st.expander("Market filters", expanded=False):
        c1, c2, c3, c4 = st.columns([1.4, 1.5, 1.7, 2.4])

        years = sorted(data["year"].dropna().astype(int).unique().tolist())
        if len(years) > 1:
            selected_year_range = c1.slider(
                "Year range",
                min_value=min(years),
                max_value=max(years),
                value=(min(years), max(years)),
                step=1,
                help="Drag either end to compare a custom period.",
            )
        else:
            selected_year_range = (years[0], years[0])
            c1.info(f"Year: {years[0]}")

        month_labels = list(MONTH_OPTIONS)
        selected_month_range = c2.select_slider(
            "Month range",
            options=month_labels,
            value=(month_labels[0], month_labels[-1]),
            help="This filters the selected months across the chosen year range.",
        )

        property_types = get_options(data, "property_type_en")
        selected_property_types = c3.multiselect(
            "Property types",
            property_types,
            default=property_types,
            format_func=format_title,
        )

        areas = get_options(data, "area_name_en")
        selected_areas = c4.multiselect(
            "Areas",
            areas,
            default=[],
            help="Leave empty to include all areas. Click and type to search.",
            format_func=format_title,
        )

    filtered = data
    start_year, end_year = selected_year_range
    filtered = filtered[filtered["year"].between(start_year, end_year)]

    start_month = MONTH_OPTIONS[selected_month_range[0]]
    end_month = MONTH_OPTIONS[selected_month_range[1]]
    filtered = filtered[filtered["month"].between(start_month, end_month)]

    if selected_property_types:
        filtered = filtered[filtered["property_type_en"].astype(str).isin(selected_property_types)]
    if selected_areas:
        filtered = filtered[filtered["area_name_en"].astype(str).isin(selected_areas)]

    return filtered


def area_map(summary: pd.DataFrame, title: str, key: str) -> None:
    mapped = summary.dropna(subset=["latitude", "longitude"]).copy()
    if mapped.empty:
        st.info("Map coordinates are not available for the selected areas yet.")
        return

    mapped["display_area"] = mapped["area_name_en"].astype(str).map(format_title)
    all_areas_option = "All mapped areas"
    area_options = [all_areas_option] + mapped["area_name_en"].astype(str).sort_values().tolist()
    selected_area = st.selectbox(
        "Search map area",
        area_options,
        key=f"{key}_area_search",
        help="Click and type to search for a Dubai area.",
        format_func=lambda value: all_areas_option if value == all_areas_option else format_title(value),
    )

    visible = mapped
    if selected_area != all_areas_option:
        selected = mapped[mapped["area_name_en"].astype(str).eq(selected_area)]
        visible = pd.concat([selected, mapped[~mapped["area_name_en"].astype(str).eq(selected_area)].head(30)])

    fig = px.scatter(
        visible,
        x="longitude",
        y="latitude",
        size="transactions",
        color="median_price_per_sqm",
        hover_name="display_area",
        hover_data={
            "transactions": ":,",
            "median_price": ":,.0f",
            "median_price_per_sqm": ":,.0f",
            "latitude": False,
            "longitude": False,
            "display_area": False,
        },
        text="display_area",
        color_continuous_scale=["#075be8", "#1fbf75", "#ff7a1a"],
        template="plotly_dark",
        height=540,
        title=title,
    )
    fig.update_traces(textposition="top center", marker=dict(line=dict(width=1, color="#ffffff")))
    fig.update_layout(
        plot_bgcolor="#0f1520",
        paper_bgcolor="#10151f",
        font_color="#eef5ff",
        xaxis_title="Longitude",
        yaxis_title="Latitude",
        margin=dict(l=10, r=10, t=55, b=10),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#293244", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#293244", zeroline=False, scaleanchor="x", scaleratio=1)

    st.plotly_chart(fig, use_container_width=True)


def home_page(data: pd.DataFrame) -> None:
    st.header("What This Dashboard Does")
    disclaimer()

    st.markdown(
        """
        This dashboard turns the notebook research into an interactive tool. The data is cleaned,
        filtered, cached, and connected to saved models so users can explore the Dubai residential
        sales market without retraining anything.

        The project has two machine-learning layers. First, a CatBoost classifier fills selected
        missing room categories. Second, an XGBoost model predicts transaction value from property,
        location, room, area, time, and transaction-context features.
        """
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Dashboard Rows", f"{len(data):,}")
    c2.metric("Areas", f"{data['area_name_en'].astype(str).nunique():,}")
    c3.metric("Years Covered", f"{int(data['year'].min())} to {int(data['year'].max())}")

    st.subheader("How To Read The App")
    definition(
        "Market Overview",
        "Use this first to understand overall transaction volume, median price, median property size, and time trends.",
    )
    definition(
        "Area Comparison",
        "Use this to compare Dubai areas by median price, price per square metre, activity level, and typical property size.",
    )
    definition(
        "Price Prediction",
        "Use this to estimate the transaction value of a property. Inputs are restricted to categories the saved XGBoost model can accept.",
    )
    definition(
        "ROI Calculator",
        "Use this for scenario analysis after estimating purchase price and rent. It calculates yield and one-year return assumptions.",
    )
    definition(
        "Investment Opportunities",
        "Use this as a screening view. The value score combines activity and relative price per square metre, but it is not investment advice.",
    )


def market_overview(data: pd.DataFrame) -> None:
    st.header("Market Overview")
    disclaimer()

    total_transactions = len(data)
    median_price = data["actual_worth"].median()
    median_area = data["procedure_area"].median()
    median_ppsqm = (data["actual_worth"] / data["procedure_area"]).median()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", f"{total_transactions:,}")
    c2.metric("Median Price", money(median_price))
    c3.metric("Median Area", f"{median_area:,.0f} sqm")
    c4.metric("Median Price / sqm", money(median_ppsqm))

    definition(
        "Median price",
        "The middle transaction value. It is usually more stable than the average because extreme luxury sales can pull the mean upward.",
    )

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
    disclaimer()

    definition(
        "Price per sqm",
        "A normalized price measure that helps compare areas even when typical property sizes are different.",
    )

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
        "Selected Areas On Coordinate Map",
        key="area_comparison_map",
    )

    st.dataframe(summary, use_container_width=True, hide_index=True)


def price_prediction(data: pd.DataFrame) -> float | None:
    st.header("Price Prediction")
    disclaimer("prediction")

    try:
        model = get_price_model()
    except Exception as exc:
        st.error(f"Could not load the price model: {exc}")
        return None

    model_data = get_prediction_data()
    if model_data.empty:
        st.error("No residential sales records are available for price prediction.")
        return None

    definition(
        "Why the dropdowns are restricted",
        "XGBoost only accepts categories stored in the trained model. The form therefore shows model-compatible residential sales categories to avoid unsupported input errors.",
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        area_name = select_from_scope("Area", model_data, "area_name_en")
        scoped = restrict_scoped_data(model_data, "area_name_en", area_name)

        property_sub_type = select_from_scope("Property subtype", scoped, "property_sub_type_en", default="flat")
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
            help="Procedure area is the registered area used in the transaction record.",
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
        st.error(f"This exact input could not be predicted with the saved XGBoost model. Details: {exc}")
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
    disclaimer("roi")

    definition(
        "Gross yield vs net yield",
        "Gross yield uses rent divided by purchase price. Net yield subtracts estimated costs and includes acquisition cost, so it is usually more realistic.",
    )

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
    disclaimer()

    summary = area_summary(data)
    summary = summary[summary["transactions"] >= 100].copy()
    summary["value_score"] = (
        summary["transactions"].rank(pct=True)
        + summary["median_price_per_sqm"].rank(pct=True, ascending=False)
    )

    definition(
        "Value score",
        "A simple screening score. It rewards areas with high transaction activity and lower median price per square metre. It is useful for shortlisting areas, not for making a final investment decision.",
    )

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


def show_image(path: Path, caption: str) -> None:
    if path.exists():
        st.image(str(path), caption=caption, use_container_width=True)
    else:
        st.warning(f"Missing figure: {path.name}")


def model_performance() -> None:
    st.header("Model Performance")
    disclaimer("prediction")

    st.subheader("Rooms Model")
    st.markdown(
        """
        The room model is a CatBoost multiclass classifier. It was trained to infer missing
        `rooms_en` categories using property type, area, registration type, procedure, parking,
        procedure area, advertised area, and time features.
        """
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Rooms Accuracy", "0.9033")
    c2.metric("Rooms Macro F1", "0.6766")
    c3.metric("Rooms Weighted F1", "0.9030")

    show_image(
        PROJECT_ROOT / "figures" / "readme" / "rooms_confusion_matrix.png",
        "Normalized confusion matrix for the room classification model.",
    )

    st.subheader("Price Model")
    st.markdown(
        """
        The price model is an XGBoost regressor trained on `log_actual_worth`.
        Predictions are converted back into AED. The log target makes training more stable
        because real estate prices are strongly right-skewed.
        """
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Final Test MAE", "AED 240,843")
    c2.metric("Final Test RMSE", "AED 598,297")
    c3.metric("Final Test R2", "0.8892")

    c1, c2 = st.columns(2)
    with c1:
        show_image(
            PROJECT_ROOT / "figures" / "readme" / "price_actual_vs_predicted.png",
            "Actual vs predicted transaction values.",
        )
    with c2:
        show_image(
            PROJECT_ROOT / "figures" / "readme" / "price_error_distribution.png",
            "Distribution of price prediction errors.",
        )

    show_image(
        PROJECT_ROOT / "figures" / "xgboost_training_validation_rmse.png",
        "Training vs validation RMSE on log price.",
    )

    show_image(
        PROJECT_ROOT / "figures" / "readme" / "xgboost_feature_importance.png",
        "XGBoost feature importance for the price model.",
    )

    definition(
        "How to interpret the metrics",
        "MAE is the average absolute AED error. RMSE penalizes large errors more heavily. R2 shows how much variation in price is explained by the model.",
    )


def main() -> None:
    apply_theme()
    page = header()

    try:
        data = get_data()
    except Exception as exc:
        st.error(f"Could not load dashboard data: {exc}")
        st.stop()

    filtered_data = top_filters(data)

    predicted_price = None
    if page == "Home":
        home_page(filtered_data)
    elif page == "Market Overview":
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
        with st.expander("Use this prediction in ROI calculator", expanded=True):
            roi_calculator(default_price=predicted_price)


if __name__ == "__main__":
    main()
