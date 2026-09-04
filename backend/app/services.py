from __future__ import annotations

import calendar
import os
import sqlite3
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from note import (
    CATEGORICAL_PRICE_FEATURES,
    DASHBOARD_DB_PATH,
    DATA_DIR,
    PRICE_FEATURES,
    align_price_categories,
    calculate_roi,
    get_price_model_categories,
    load_area_coordinates,
    load_price_model,
    make_prediction_row,
    predict_prices,
    prepare_dashboard_data,
    prepare_price_features,
)


PREDICTION_COLUMNS = [
    "area_name_en",
    "property_sub_type_en",
    "property_type_en",
    "property_usage_en",
    "rooms_en",
    "reg_type_en",
    "procedure_name_en",
]

PREDICTION_BASE_COLUMNS = [
    "actual_worth",
    "procedure_area",
    *PRICE_FEATURES,
]


def _download_file(url: str, destination: Path, token: str | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    temporary = destination.with_suffix(destination.suffix + ".download")
    with urllib.request.urlopen(request, timeout=120) as response:
        with temporary.open("wb") as file:
            file.write(response.read())
    temporary.replace(destination)


@lru_cache(maxsize=1)
def database_path() -> Path:
    if DASHBOARD_DB_PATH.exists():
        return DASHBOARD_DB_PATH

    db_url = os.getenv("DASHBOARD_DB_URL")
    if db_url:
        _download_file(db_url, DASHBOARD_DB_PATH, token=os.getenv("DASHBOARD_DATA_TOKEN"))
        return DASHBOARD_DB_PATH

    prepare_dashboard_data()
    if not DASHBOARD_DB_PATH.exists():
        raise FileNotFoundError(
            "Dashboard database was not found. Add data/dashboard.sqlite locally "
            "or set DASHBOARD_DB_URL for deployment."
        )
    return DASHBOARD_DB_PATH


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(database_path())
    connection.row_factory = sqlite3.Row
    return connection


def _read_sql(query: str, params: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
    with _connect() as connection:
        return pd.read_sql_query(query, connection, params=params or [])


def _placeholders(values: list[Any]) -> str:
    return ",".join(["?"] * len(values))


def _market_where(
    years: list[int] | None = None,
    property_types: list[str] | None = None,
    areas: list[str] | None = None,
) -> tuple[str, list[Any]]:
    clauses = [
        "actual_worth IS NOT NULL",
        "actual_worth > 0",
        "procedure_area IS NOT NULL",
        "procedure_area > 0",
    ]
    params: list[Any] = []

    if years:
        clauses.append(f"CAST(year AS INTEGER) IN ({_placeholders(years)})")
        params.extend(years)
    if property_types:
        clauses.append(f"property_type_en IN ({_placeholders(property_types)})")
        params.extend(property_types)
    if areas:
        clauses.append(f"area_name_en IN ({_placeholders(areas)})")
        params.extend(areas)

    return " AND ".join(clauses), params


@lru_cache(maxsize=1)
def price_model():
    return load_price_model()


@lru_cache(maxsize=1)
def price_model_categories() -> dict[str, list[str]]:
    return get_price_model_categories(price_model())


def _prediction_where(scopes: dict[str, str] | None = None) -> tuple[str, list[Any]]:
    clauses = [
        "actual_worth IS NOT NULL",
        "actual_worth > 0",
        "procedure_area IS NOT NULL",
        "procedure_area > 0",
        "rooms_en IS NOT NULL",
    ]
    params: list[Any] = []

    for column, values in price_model_categories().items():
        if column in CATEGORICAL_PRICE_FEATURES and values:
            clauses.append(f"{column} IN ({_placeholders(values)})")
            params.extend(values)

    for column, value in (scopes or {}).items():
        if column in PREDICTION_COLUMNS and value:
            clauses.append(f"{column} = ?")
            params.append(value)

    return " AND ".join(clauses), params


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.replace({np.nan: None}).to_dict(orient="records")


def options() -> dict[str, list[Any]]:
    years = _read_sql(
        "SELECT DISTINCT CAST(year AS INTEGER) AS year FROM transactions "
        "WHERE year IS NOT NULL ORDER BY year"
    )["year"].dropna().astype(int).tolist()
    property_types = _read_sql(
        "SELECT DISTINCT property_type_en FROM transactions "
        "WHERE property_type_en IS NOT NULL ORDER BY property_type_en"
    )["property_type_en"].astype(str).tolist()
    areas = _read_sql(
        "SELECT DISTINCT area_name_en FROM transactions "
        "WHERE area_name_en IS NOT NULL ORDER BY area_name_en"
    )["area_name_en"].astype(str).tolist()

    return {
        "years": years,
        "months": [{"label": calendar.month_name[i], "value": i} for i in range(1, 13)],
        "property_types": property_types,
        "areas": areas,
    }


def overview(
    years: list[int] | None = None,
    property_types: list[str] | None = None,
    areas: list[str] | None = None,
) -> dict[str, Any]:
    where_sql, params = _market_where(years, property_types, areas)
    columns = "instance_date, actual_worth, procedure_area"
    dataset = _read_sql(f"SELECT {columns} FROM transactions WHERE {where_sql}", params)
    if dataset.empty:
        return {"metrics": {"transactions": 0, "median_price": None, "median_area": None, "median_price_per_sqm": None}, "monthly": []}

    dataset["instance_date"] = pd.to_datetime(dataset["instance_date"], errors="coerce")
    dataset["price_per_sqm"] = dataset["actual_worth"] / dataset["procedure_area"].replace(0, np.nan)
    monthly = (
        dataset
        .dropna(subset=["instance_date", "actual_worth"])
        .assign(month_start=lambda df: df["instance_date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month_start", observed=True)
        .agg(transactions=("actual_worth", "size"), median_price=("actual_worth", "median"))
        .reset_index()
        .sort_values("month_start")
    )

    return {
        "metrics": {
            "transactions": int(len(dataset)),
            "median_price": float(dataset["actual_worth"].median()),
            "median_area": float(dataset["procedure_area"].median()),
            "median_price_per_sqm": float(dataset["price_per_sqm"].median()),
        },
        "monthly": [
            {
                "month_start": row.month_start.strftime("%Y-%m-%d"),
                "transactions": int(row.transactions),
                "median_price": float(row.median_price),
            }
            for row in monthly.itertuples()
        ],
    }


def area_summary(
    years: list[int] | None = None,
    property_types: list[str] | None = None,
    areas: list[str] | None = None,
    min_transactions: int = 25,
) -> list[dict[str, Any]]:
    where_sql, params = _market_where(years, property_types, areas)
    dataset = _read_sql(
        f"""
        SELECT area_name_en, actual_worth, procedure_area
        FROM transactions
        WHERE {where_sql}
          AND area_name_en IS NOT NULL
        """,
        params,
    )
    if dataset.empty:
        return []

    dataset["price_per_sqm"] = dataset["actual_worth"] / dataset["procedure_area"].replace(0, np.nan)
    summary = (
        dataset
        .groupby("area_name_en", observed=True)
        .agg(
            transactions=("actual_worth", "size"),
            median_price=("actual_worth", "median"),
            mean_price=("actual_worth", "mean"),
            median_price_per_sqm=("price_per_sqm", "median"),
            median_area=("procedure_area", "median"),
        )
        .reset_index()
    )
    summary = summary[summary["transactions"].ge(min_transactions)]
    coordinates = load_area_coordinates()
    summary = summary.merge(coordinates, on="area_name_en", how="left")
    summary = summary.sort_values("transactions", ascending=False)
    return _records(summary)


def prediction_options(scopes: dict[str, str] | None = None) -> dict[str, Any]:
    scopes = scopes or {}
    result: dict[str, Any] = {}

    for column in PREDICTION_COLUMNS:
        narrowed = {key: value for key, value in scopes.items() if key != column}
        where_sql, params = _prediction_where(narrowed)
        values = _read_sql(
            f"""
            SELECT DISTINCT {column}
            FROM transactions
            WHERE {where_sql}
              AND {column} IS NOT NULL
            ORDER BY {column}
            """,
            params,
        )[column].dropna().astype(str).tolist()
        allowed = price_model_categories().get(column)
        if allowed:
            values = [value for value in values if value in allowed]
        result[column] = values

    where_sql, params = _prediction_where(scopes)
    area_row = _read_sql(
        f"SELECT AVG(procedure_area) AS typical_area FROM transactions WHERE {where_sql}",
        params,
    )
    typical_area = area_row.loc[0, "typical_area"] if not area_row.empty else np.nan
    result["median_area"] = 100.0 if pd.isna(typical_area) else float(typical_area)
    return result


def _infer_advertised_area(payload: dict[str, Any]) -> str:
    supplied = payload.get("advertised_area")
    if supplied:
        return str(supplied)

    scopes = {"area_name_en": str(payload["area_name_en"])}
    where_sql, params = _prediction_where(scopes)
    values = _read_sql(
        f"""
        SELECT advertised_area, COUNT(*) AS records
        FROM transactions
        WHERE {where_sql}
          AND advertised_area IS NOT NULL
        GROUP BY advertised_area
        ORDER BY records DESC
        LIMIT 1
        """,
        params,
    )
    if not values.empty:
        return str(values.loc[0, "advertised_area"])
    return str(payload["area_name_en"])


def predict_price(payload: dict[str, Any]) -> dict[str, Any]:
    clean_payload = {
        key: (value.lower() if isinstance(value, str) else value)
        for key, value in payload.items()
        if value is not None
    }
    clean_payload["advertised_area"] = _infer_advertised_area(clean_payload)

    row = make_prediction_row(**clean_payload)
    features = prepare_price_features(row)
    features = align_price_categories(features, price_model_categories())
    predicted_price = float(predict_prices(price_model(), features)[0])

    similar = _read_sql(
        """
        SELECT actual_worth
        FROM transactions
        WHERE actual_worth IS NOT NULL
          AND actual_worth > 0
          AND area_name_en = ?
          AND property_sub_type_en = ?
          AND rooms_en = ?
        """,
        [
            clean_payload["area_name_en"],
            clean_payload["property_sub_type_en"],
            clean_payload["rooms_en"],
        ],
    )
    median_similar = None
    if len(similar) >= 10:
        median_similar = float(similar["actual_worth"].median())

    return {
        "predicted_price": predicted_price,
        "predicted_price_per_sqm": predicted_price / float(clean_payload["procedure_area"]),
        "similar_median_price": median_similar,
        "similar_count": int(len(similar)),
        "advertised_area_used": clean_payload["advertised_area"],
    }


def roi(payload: dict[str, Any]) -> dict[str, float | None]:
    result = calculate_roi(**payload)
    return {key: None if pd.isna(value) else float(value) for key, value in result.items()}


def opportunities(
    years: list[int] | None = None,
    property_types: list[str] | None = None,
    areas: list[str] | None = None,
) -> list[dict[str, Any]]:
    summary = pd.DataFrame(area_summary(years, property_types, areas, min_transactions=100))
    if summary.empty:
        return []

    summary["value_score"] = (
        summary["transactions"].rank(pct=True)
        + summary["median_price_per_sqm"].rank(pct=True, ascending=False)
    )
    summary = summary.sort_values("value_score", ascending=False).head(25)
    return _records(summary)


def model_performance() -> dict[str, Any]:
    return {
        "rooms_model": {
            "model": "CatBoost multiclass classifier",
            "accuracy": 0.9033,
            "macro_f1": 0.6766,
            "weighted_f1": 0.9030,
        },
        "price_model": {
            "model": "XGBoost regressor",
            "target": "log_actual_worth",
            "mae": 240843.49,
            "rmse": 598296.59,
            "r2": 0.8892,
        },
        "figures": {
            "rooms_confusion_matrix": "/figures/readme/rooms_confusion_matrix.png",
            "price_actual_vs_predicted": "/figures/readme/price_actual_vs_predicted.png",
            "price_error_distribution": "/figures/readme/price_error_distribution.png",
            "xgboost_training_validation_rmse": "/figures/xgboost_training_validation_rmse.png",
            "xgboost_feature_importance": "/figures/readme/xgboost_feature_importance.png",
        },
    }
