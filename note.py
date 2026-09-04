from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from xgboost import XGBRegressor


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"

PRICE_MODEL_PATH = MODELS_DIR / "xgboost_price_model.json"
ROOMS_MODEL_PATH = MODELS_DIR / "rooms_en_production_final_model.cbm"
DASHBOARD_DB_PATH = DATA_DIR / "dashboard.sqlite"
DASHBOARD_CACHE_PATH = DATA_DIR / "dashboard_cache.parquet"

PRICE_FEATURES = [
    "procedure_name_en",
    "property_type_en",
    "property_sub_type_en",
    "property_usage_en",
    "reg_type_en",
    "area_name_en",
    "rooms_en",
    "has_parking",
    "procedure_area",
    "advertised_area",
    "year",
    "month",
]

CATEGORICAL_PRICE_FEATURES = [
    "procedure_name_en",
    "property_type_en",
    "property_sub_type_en",
    "property_usage_en",
    "reg_type_en",
    "area_name_en",
    "rooms_en",
    "advertised_area",
]

PRICE_MODEL_PROPERTY_SUBTYPES = [
    "flat",
    "villa",
    "hotel_apartment",
    "hotel_rooms",
    "stacked_townhouses",
]

PRICE_MODEL_EXCLUDED_ROOMS = ["shop", "office"]

AREA_COORDINATES = {
    "abu hail": (25.2854, 55.3291),
    "al barsha first": (25.1111, 55.2032),
    "al barsha south fourth": (25.0603, 55.2405),
    "al barsha south fifth": (25.0476, 55.2042),
    "al hebiah fifth": (25.0577, 55.2466),
    "al khail heights": (25.1841, 55.2702),
    "al kifaf": (25.2339, 55.2926),
    "al merkadh": (25.1544, 55.3134),
    "al thanyah fifth": (25.0752, 55.1517),
    "business bay": (25.1850, 55.2732),
    "burj khalifa": (25.1972, 55.2744),
    "dubai investment park first": (24.9800, 55.1800),
    "dubai marina": (25.0800, 55.1400),
    "jabal ali first": (25.0217, 55.1270),
    "jumeirah first": (25.2303, 55.2644),
    "jumeirah lakes towers": (25.0694, 55.1413),
    "jumeirah village circle": (25.0600, 55.2089),
    "jumeirah village triangle": (25.0434, 55.1888),
    "marsaal dubai": (25.2510, 55.2850),
    "nad al sheba first": (25.1555, 55.3577),
    "palm jumeirah": (25.1124, 55.1390),
    "tecom site a": (25.0953, 55.1723),
    "wadi al safa 5": (25.0706, 55.3266),
    "wadi al safa 7": (25.0896, 55.3685),
    "warsan first": (25.1628, 55.4211),
    "warsan fourth": (25.1558, 55.3954),
    "zaabeel first": (25.2171, 55.2847),
}


def _normalize_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.lower()


def _existing(columns: Iterable[str], df: pd.DataFrame) -> list[str]:
    return [column for column in columns if column in df.columns]


def map_advertised_area(df: pd.DataFrame, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Add or fill advertised_area using the Dubai area alias mapping file."""

    df = df.copy()
    mapping_path = data_dir / "dubai_area_alias_mapping.csv"

    if not mapping_path.exists() or "area_name_en" not in df.columns:
        if "advertised_area" not in df.columns and "area_name_en" in df.columns:
            df["advertised_area"] = _normalize_text(df["area_name_en"]).astype("category")
        return df

    area_mapping = pd.read_csv(mapping_path)
    area_mapping["official_area"] = _normalize_text(area_mapping["official_area"])
    area_mapping["advertised_area"] = _normalize_text(area_mapping["advertised_area"])

    area_map = (
        area_mapping
        .dropna(subset=["official_area", "advertised_area"])
        .groupby("official_area", observed=True)["advertised_area"]
        .agg(lambda values: " | ".join(sorted(set(values))))
    )

    normalized_area = _normalize_text(df["area_name_en"])
    mapped_area = normalized_area.map(area_map)

    if "advertised_area" not in df.columns:
        df["advertised_area"] = pd.NA

    df["advertised_area"] = (
        df["advertised_area"]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
        .fillna(mapped_area)
        .fillna(normalized_area)
        .astype("category")
    )

    return df


def standardize_new_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Rename newer Dubai Land Department columns to the project schema."""

    rename_columns = {
        "TRANSACTION_NUMBER": "transaction_id",
        "INSTANCE_DATE": "instance_date",
        "GROUP_EN": "trans_group_en",
        "PROCEDURE_EN": "procedure_name_en",
        "IS_OFFPLAN_EN": "reg_type_en",
        "USAGE_EN": "property_usage_en",
        "AREA_EN": "area_name_en",
        "PROP_TYPE_EN": "property_type_en",
        "PROP_SB_TYPE_EN": "property_sub_type_en",
        "TRANS_VALUE": "actual_worth",
        "PROCEDURE_AREA": "procedure_area",
        "ROOMS_EN": "rooms_en",
        "PARKING": "has_parking",
        "NEAREST_METRO_EN": "nearest_metro_en",
        "NEAREST_MALL_EN": "nearest_mall_en",
        "NEAREST_LANDMARK_EN": "nearest_landmark_en",
        "MASTER_PROJECT_EN": "master_project_en",
        "PROJECT_EN": "project_name_en",
    }

    df = df.rename(columns=rename_columns).copy()

    if "actual_worth" in df.columns and "procedure_area" in df.columns:
        actual_worth = pd.to_numeric(df["actual_worth"], errors="coerce")
        procedure_area = pd.to_numeric(df["procedure_area"], errors="coerce")
        df["meter_sale_price"] = actual_worth / procedure_area.mask(procedure_area.eq(0))

    if "reg_type_en" in df.columns:
        df["reg_type_en"] = _normalize_text(df["reg_type_en"]).replace({
            "off-plan": "off-plan properties",
            "ready": "existing properties",
        })

    if "procedure_name_en" in df.columns:
        df["procedure_name_en"] = _normalize_text(df["procedure_name_en"]).replace({
            "sale": "sell",
        })

    if "trans_group_en" in df.columns:
        df["trans_group_en"] = _normalize_text(df["trans_group_en"]).replace({
            "mortgage": "mortgages",
        })

    return df


def clean_transaction_data(df: pd.DataFrame) -> pd.DataFrame:
    """Return a cleaned transaction DataFrame using the notebook schema."""

    df = df.copy()
    df.columns = df.columns.str.strip()

    use_columns = [
        "trans_group_en",
        "procedure_name_en",
        "instance_date",
        "property_type_en",
        "property_sub_type_en",
        "property_usage_en",
        "reg_type_en",
        "area_name_en",
        "rooms_en",
        "has_parking",
        "procedure_area",
        "actual_worth",
        "meter_sale_price",
        "advertised_area",
    ]
    df = df[_existing(use_columns, df)].copy()

    category_columns = [
        "trans_group_en",
        "procedure_name_en",
        "property_type_en",
        "property_sub_type_en",
        "property_usage_en",
        "reg_type_en",
        "area_name_en",
        "rooms_en",
        "advertised_area",
    ]
    for column in _existing(category_columns, df):
        df[column] = _normalize_text(df[column]).astype("category")

    if "instance_date" in df.columns:
        df["instance_date"] = pd.to_datetime(
            df["instance_date"],
            dayfirst=True,
            errors="coerce",
        ).dt.normalize()

    for column in _existing(["procedure_area", "actual_worth", "meter_sale_price"], df):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if "has_parking" in df.columns:
        parking = _normalize_text(df["has_parking"])
        df["has_parking"] = parking.isin(["1", "true", "yes", "y", "available"])

    return df


def remove_price_outliers(df: pd.DataFrame, quantile: float = 0.001) -> pd.DataFrame:
    """Remove only the most extreme price, area, and price-per-area values."""

    df_filtered = df.copy()
    for column in _existing(["actual_worth", "procedure_area", "meter_sale_price"], df_filtered):
        low = df_filtered[column].quantile(quantile)
        high = df_filtered[column].quantile(1 - quantile)
        df_filtered = df_filtered[df_filtered[column].between(low, high)]
    return df_filtered.copy()


def filter_price_model_domain(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows that match the residential sales domain used by the price model."""

    filtered = df.copy()

    if "trans_group_en" in filtered.columns:
        filtered = filtered[filtered["trans_group_en"].astype(str).eq("sales")]

    if "property_sub_type_en" in filtered.columns:
        filtered = filtered[
            filtered["property_sub_type_en"].astype(str).isin(PRICE_MODEL_PROPERTY_SUBTYPES)
        ]

    if "rooms_en" in filtered.columns:
        filtered = filtered[
            ~filtered["rooms_en"].astype(str).isin(PRICE_MODEL_EXCLUDED_ROOMS)
        ]

    return filtered.copy()


def _load_raw_dashboard_data(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Load, clean, combine, and lightly filter local transaction files."""

    frames = []

    old_path = data_dir / "Transactions.csv"
    if old_path.exists():
        old_df = pd.read_csv(old_path, low_memory=False)
        old_df = map_advertised_area(old_df, data_dir=data_dir)
        frames.append(clean_transaction_data(old_df))

    new_path = data_dir / "transactions-2026-07-10.csv"
    if new_path.exists():
        new_df = pd.read_csv(new_path, low_memory=False)
        new_df = standardize_new_transactions(new_df)
        new_df = map_advertised_area(new_df, data_dir=data_dir)
        frames.append(clean_transaction_data(new_df))

    if not frames:
        raise FileNotFoundError("No transaction CSV files were found in the data folder.")

    data = pd.concat(frames, ignore_index=True)
    data = data[
        data["actual_worth"].notna()
        & data["actual_worth"].gt(0)
        & data["procedure_area"].notna()
        & data["procedure_area"].gt(0)
    ].copy()

    if "instance_date" in data.columns:
        data["year"] = data["instance_date"].dt.year
        data["month"] = data["instance_date"].dt.month

    return remove_price_outliers(data)


def _write_dashboard_storage(data: pd.DataFrame) -> None:
    """Persist cleaned dashboard data for fast Streamlit startup."""

    DASHBOARD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(DASHBOARD_CACHE_PATH, index=False)

    sqlite_data = data.copy()
    for column in sqlite_data.select_dtypes(include=["category"]).columns:
        sqlite_data[column] = sqlite_data[column].astype("string")

    with sqlite3.connect(DASHBOARD_DB_PATH) as connection:
        sqlite_data.to_sql("transactions", connection, if_exists="replace", index=False)


def build_dashboard_database(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Build the local SQLite/parquet dashboard cache from the raw CSV files."""

    data = _load_raw_dashboard_data(data_dir=data_dir)
    _write_dashboard_storage(data)
    return data


def prepare_dashboard_data(data_dir: Path = DATA_DIR, force_rebuild: bool = False) -> pd.DataFrame:
    """Load cleaned dashboard data from cache, building it once if needed."""

    if not force_rebuild and DASHBOARD_CACHE_PATH.exists():
        try:
            return pd.read_parquet(DASHBOARD_CACHE_PATH)
        except ImportError:
            if not DASHBOARD_DB_PATH.exists():
                raise

    if not force_rebuild and DASHBOARD_DB_PATH.exists():
        with sqlite3.connect(DASHBOARD_DB_PATH) as connection:
            data = pd.read_sql_query(
                "SELECT * FROM transactions",
                connection,
                parse_dates=["instance_date"],
            )
        if not DASHBOARD_CACHE_PATH.exists():
            try:
                data.to_parquet(DASHBOARD_CACHE_PATH, index=False)
            except ImportError:
                pass
        return data

    return build_dashboard_database(data_dir=data_dir)


def load_area_coordinates() -> pd.DataFrame:
    """Return approximate map coordinates for commonly used Dubai areas."""

    return pd.DataFrame(
        [
            {"area_name_en": area, "latitude": coords[0], "longitude": coords[1]}
            for area, coords in AREA_COORDINATES.items()
        ]
    )


def prepare_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare feature columns in the format expected by the XGBoost price model."""

    missing = [column for column in PRICE_FEATURES if column not in df.columns]
    if missing:
        raise KeyError(f"Missing price feature columns: {missing}")

    features = df[PRICE_FEATURES].copy()

    if "has_parking" in features.columns:
        features["has_parking"] = features["has_parking"].astype("int8")

    for column in CATEGORICAL_PRICE_FEATURES:
        features[column] = (
            features[column]
            .astype("string")
            .str.strip()
            .str.lower()
            .fillna("unknown")
            .astype("category")
        )

    numeric_features = [column for column in features.columns if column not in CATEGORICAL_PRICE_FEATURES]
    for column in numeric_features:
        features[column] = pd.to_numeric(features[column], errors="coerce")

    return features


def load_price_model(path: Path = PRICE_MODEL_PATH) -> XGBRegressor:
    model = XGBRegressor()
    model.load_model(path)
    return model


def get_price_model_categories(model: XGBRegressor) -> dict[str, list[str]]:
    """Return categorical values stored inside a fitted XGBoost model."""

    booster = model.get_booster()
    categories = booster.get_categories(export_to_arrow=True).to_arrow()

    category_values: dict[str, list[str]] = {}
    for feature_name, values in categories:
        if values is not None:
            category_values[feature_name] = [str(value) for value in values.to_pylist()]

    return category_values


def load_rooms_model(path: Path = ROOMS_MODEL_PATH) -> CatBoostClassifier:
    model = CatBoostClassifier()
    model.load_model(path)
    return model


def align_price_categories(
    features: pd.DataFrame,
    category_values: dict[str, list[str]],
) -> pd.DataFrame:
    """Align categorical feature dtypes with the saved XGBoost model."""

    aligned = features.copy()
    for column, values in category_values.items():
        if column in aligned.columns:
            aligned[column] = pd.Categorical(aligned[column].astype("string"), categories=values)

    missing_categories = [
        column
        for column in category_values
        if column in aligned.columns and aligned[column].isna().any()
    ]
    if missing_categories:
        raise ValueError(
            "Unsupported model category in: "
            + ", ".join(missing_categories)
        )

    return aligned


def predict_prices(model: XGBRegressor, features: pd.DataFrame) -> np.ndarray:
    """Predict AED prices from prepared XGBoost features."""

    predicted_log_price = model.predict(features)
    predicted_price = np.expm1(predicted_log_price)
    return np.clip(predicted_price, 0, None)


def make_prediction_row(
    procedure_name_en: str,
    property_type_en: str,
    property_sub_type_en: str,
    property_usage_en: str,
    reg_type_en: str,
    area_name_en: str,
    rooms_en: str,
    has_parking: bool,
    procedure_area: float,
    advertised_area: str,
    year: int,
    month: int,
) -> pd.DataFrame:
    """Create a one-row DataFrame for price prediction."""

    return pd.DataFrame([{
        "procedure_name_en": procedure_name_en,
        "property_type_en": property_type_en,
        "property_sub_type_en": property_sub_type_en,
        "property_usage_en": property_usage_en,
        "reg_type_en": reg_type_en,
        "area_name_en": area_name_en,
        "rooms_en": rooms_en,
        "has_parking": has_parking,
        "procedure_area": procedure_area,
        "advertised_area": advertised_area,
        "year": year,
        "month": month,
    }])


def calculate_roi(
    purchase_price: float,
    monthly_rent: float,
    annual_costs: float = 0.0,
    closing_cost_rate: float = 0.04,
    vacancy_rate: float = 0.05,
    appreciation_rate: float = 0.03,
) -> dict[str, float]:
    """Calculate simple rental ROI and one-year total return metrics."""

    acquisition_cost = purchase_price * (1 + closing_cost_rate)
    annual_gross_rent = monthly_rent * 12
    effective_rent = annual_gross_rent * (1 - vacancy_rate)
    annual_net_income = effective_rent - annual_costs
    gross_yield = annual_gross_rent / purchase_price if purchase_price else np.nan
    net_yield = annual_net_income / acquisition_cost if acquisition_cost else np.nan
    estimated_appreciation = purchase_price * appreciation_rate
    one_year_total_return = annual_net_income + estimated_appreciation
    one_year_roi = one_year_total_return / acquisition_cost if acquisition_cost else np.nan

    return {
        "purchase_price": purchase_price,
        "acquisition_cost": acquisition_cost,
        "annual_gross_rent": annual_gross_rent,
        "annual_net_income": annual_net_income,
        "gross_yield": gross_yield,
        "net_yield": net_yield,
        "estimated_appreciation": estimated_appreciation,
        "one_year_total_return": one_year_total_return,
        "one_year_roi": one_year_roi,
    }
