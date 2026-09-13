from __future__ import annotations

import calendar
import json
import os
import shutil
import sqlite3
import urllib.request
from contextlib import closing
from functools import lru_cache, wraps
from pathlib import Path
from threading import RLock
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
    prepare_price_features,
)

from .analytics_sql import summarize, quantiles
from .precomputed import signature


# Bound simultaneous expensive work in this process, including cold model loading.
_work_lock = RLock()


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _work_lock:
            return function(*args, **kwargs)
    return wrapped


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
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as file:
            shutil.copyfileobj(response, file, length=1024 * 1024)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


@serialized
@lru_cache(maxsize=1)
def database_path() -> Path:
    if DASHBOARD_DB_PATH.exists():
        return DASHBOARD_DB_PATH

    db_url = os.getenv("DASHBOARD_DB_URL")
    if db_url:
        _download_file(db_url, DASHBOARD_DB_PATH, token=os.getenv("DASHBOARD_DATA_TOKEN"))
        return DASHBOARD_DB_PATH

    raise FileNotFoundError(
        "Dashboard database was not found. Prepare data/dashboard.sqlite offline "
        "or set DASHBOARD_DB_URL to the prepared SQLite download URL. "
        "The web server does not build the database from raw CSV files."
    )


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(database_path().resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute("PRAGMA cache_size=-4096")
    connection.execute("PRAGMA temp.cache_size=-4096")
    connection.execute("PRAGMA mmap_size=0")
    connection.row_factory = sqlite3.Row
    return connection


def _read_sql(query: str, params: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
    with closing(_connect()) as connection:
        return pd.read_sql_query(query, connection, params=params or [])


def _placeholders(values: list[Any]) -> str:
    return ",".join(["?"] * len(values))


def _market_where(
    years: list[int] | None = None,
    property_types: list[str] | None = None,
    areas: list[str] | None = None,
    min_price: float = 0,
    max_price: float | None = None,
) -> tuple[str, list[Any]]:
    clauses = [
        "trans_group_en = 'sales'",
        "actual_worth IS NOT NULL",
        "actual_worth > 0",
        "procedure_area IS NOT NULL",
        "procedure_area > 0",
    ]
    params: list[Any] = []
    if max_price is not None and max_price < min_price:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Maximum price must be at least the minimum price.")
    if min_price:
        clauses.append("actual_worth >= ?")
        params.append(min_price)
    if max_price is not None:
        clauses.append("actual_worth <= ?")
        params.append(max_price)

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


@serialized
@lru_cache(maxsize=1)
def price_model():
    from note import PRICE_MODEL_PATH
    binary = PRICE_MODEL_PATH.with_suffix(".ubj")
    if os.getenv("RENDER") and not binary.exists():
        raise RuntimeError("Run python -m backend.prepare_deployment in the Render build command before starting the API.")
    model = load_price_model(binary if binary.exists() else PRICE_MODEL_PATH)
    model.set_params(n_jobs=1)
    return model


@lru_cache(maxsize=1)
def price_model_categories() -> dict[str, list[str]]:
    return get_price_model_categories(price_model())


def _prediction_where(scopes: dict[str, str] | None = None) -> tuple[str, list[Any]]:
    clauses = [
        "trans_group_en = 'sales'",
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


@lru_cache(maxsize=1)
def area_aliases() -> dict[str, list[str]]:
    path = DATA_DIR / "dubai_area_alias_mapping.csv"
    if not path.exists():
        return {}
    aliases = pd.read_csv(path).dropna(subset=["official_area", "advertised_area"])
    for column in aliases:
        aliases[column] = aliases[column].str.strip().str.lower()
    return {name: sorted(set(group.advertised_area) - {name}) for name, group in aliases.groupby("official_area")}


@serialized
@lru_cache(maxsize=1)
def options() -> dict[str, Any]:
    years = _read_sql(
        "SELECT DISTINCT CAST(year AS INTEGER) AS year FROM transactions "
        "WHERE year IS NOT NULL AND trans_group_en = 'sales' ORDER BY year"
    )["year"].dropna().astype(int).tolist()
    property_types = _read_sql(
        "SELECT DISTINCT property_type_en FROM transactions "
        "WHERE property_type_en IS NOT NULL AND trans_group_en = 'sales' ORDER BY property_type_en"
    )["property_type_en"].astype(str).tolist()
    areas = _read_sql(
        "SELECT DISTINCT area_name_en FROM transactions "
        "WHERE area_name_en IS NOT NULL AND trans_group_en = 'sales' ORDER BY area_name_en"
    )["area_name_en"].astype(str).tolist()

    return {
        "years": years,
        "months": [{"label": calendar.month_name[i], "value": i} for i in range(1, 13)],
        "property_types": property_types,
        "areas": areas,
        "area_aliases": {area: area_aliases().get(area, []) for area in areas},
        "coverage": _read_sql("SELECT MIN(instance_date) AS start, MAX(instance_date) AS end, MAX(actual_worth) AS max_price FROM transactions WHERE trans_group_en = 'sales'").iloc[0].to_dict(),
    }


@lru_cache(maxsize=8)
def _market_summary_cached(years: tuple, property_types: tuple, areas: tuple, min_price: float, max_price: float | None) -> tuple:
    where, params = _market_where(list(years), list(property_types), list(areas), min_price, max_price)
    prepared = _prepared_market_summaries().get((years, property_types, areas, min_price, max_price))
    if prepared is not None:
        return prepared
    with closing(_connect()) as connection:
        return summarize(connection, where, params)


@lru_cache(maxsize=1)
def _prepared_market_summaries() -> dict:
    path = DATA_DIR / 'market_summaries.json'
    if not path.exists():
        return {}
    try:
        with path.open(encoding='utf-8') as source:
            prepared = json.load(source)
        if prepared['signature'] != signature(database_path()):
            return {}
        return {(tuple(item['years']), (), (), 0, None): (item['overview'], item['areas'])
                for item in prepared['summaries']}
    except (OSError, ValueError, KeyError, TypeError):
        # An absent, stale, or interrupted artifact never changes analytics results.
        return {}


def _market_summary(years, property_types, areas, min_price, max_price):
    # Cache only small response summaries; equivalent selections share a key.
    with _work_lock:
        return _market_summary_cached(tuple(sorted(set(years or []))),
                                      tuple(sorted(set(property_types or []))),
                                      tuple(sorted(set(areas or []))), min_price, max_price)


def overview(years=None, property_types=None, areas=None, min_price=0, max_price=None) -> dict[str, Any]:
    return _market_summary(years, property_types, areas, min_price, max_price)[0]


def area_summary(years=None, property_types=None, areas=None, min_transactions=25,
                 min_price=0, max_price=None) -> list[dict[str, Any]]:
    records = _market_summary(years, property_types, areas, min_price, max_price)[1]
    summary = pd.DataFrame([row for row in records if row['transactions'] >= min_transactions])
    if summary.empty:
        return []
    coordinates = load_area_coordinates()
    # Match official names to existing coordinates through the supplied alias file.
    known = coordinates.set_index("area_name_en")
    additions = []
    for official, aliases in area_aliases().items():
        matches = [alias for alias in aliases if alias in known.index]
        if official not in known.index and len(matches) == 1:
            additions.append({"area_name_en": official, **known.loc[matches[0]].to_dict()})
    if additions:
        coordinates = pd.concat([coordinates, pd.DataFrame(additions)], ignore_index=True)
    summary = summary.merge(coordinates, on="area_name_en", how="left")
    summary = summary.sort_values("transactions", ascending=False)
    return _records(summary)


_prediction_lock = RLock()


@lru_cache(maxsize=1)
def _prediction_profiles() -> pd.DataFrame:
    where, params = _prediction_where()
    columns = ", ".join(PREDICTION_COLUMNS)
    return _read_sql(f"SELECT {columns}, SUM(procedure_area) AS total_area, COUNT(*) AS records FROM transactions WHERE {where} GROUP BY {columns}", params)


@serialized
def prediction_options(scopes: dict[str, str] | None = None) -> dict[str, Any]:
    scopes = scopes or {}
    result: dict[str, Any] = {}
    with _prediction_lock:
        profiles = _prediction_profiles()
    for column in PREDICTION_COLUMNS:
        narrowed = profiles
        for key, value in scopes.items():
            if key in PREDICTION_COLUMNS and key != column and value:
                narrowed = narrowed[narrowed[key].eq(value)]
        result[column] = sorted(narrowed[column].dropna().astype(str).unique().tolist())
    result["years"] = [year for year in options()["years"] if year >= 2000]
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


@serialized
def predict_price(payload: dict[str, Any]) -> dict[str, Any]:
    asking_price = payload.get("asking_price")
    clean_payload = {
        key: (value.lower() if isinstance(value, str) else value)
        for key, value in payload.items()
        if value is not None and key != "asking_price"
    }
    if clean_payload["year"] not in options()["years"]:
        raise ValueError("Choose a year covered by the historical data. Use ROI scenarios for future values.")
    clean_payload["advertised_area"] = _infer_advertised_area(clean_payload)

    row = make_prediction_row(**clean_payload)
    features = prepare_price_features(row)
    features = align_price_categories(features, price_model_categories())
    predicted_price = float(predict_prices(price_model(), features)[0])

    with closing(_connect()) as connection:
        connection.execute(
            """
            CREATE TEMP TABLE similar AS SELECT actual_worth
            FROM transactions
            WHERE actual_worth IS NOT NULL
              AND trans_group_en = 'sales'
              AND actual_worth > 0
              AND area_name_en = ?
              AND property_sub_type_en = ?
              AND rooms_en = ?
              AND property_type_en = ?
              AND reg_type_en = ?
              AND procedure_area BETWEEN ? AND ?
              AND instance_date >= ? AND instance_date < ?
            """,
            [
                clean_payload["area_name_en"],
                clean_payload["property_sub_type_en"],
                clean_payload["rooms_en"],
                clean_payload["property_type_en"],
                clean_payload["reg_type_en"],
                clean_payload["procedure_area"] * 0.75,
                clean_payload["procedure_area"] * 1.25,
                (pd.Timestamp(year=clean_payload["year"], month=clean_payload["month"], day=1) - pd.DateOffset(months=35)).strftime("%Y-%m-%d"),
                (pd.Timestamp(year=clean_payload["year"], month=clean_payload["month"], day=1) + pd.DateOffset(months=1)).strftime("%Y-%m-%d"),
            ],
        )
        similar_count = connection.execute("SELECT COUNT(*) FROM similar").fetchone()[0]
        band = quantiles(connection, "similar", "actual_worth").get("all") if similar_count >= 10 else None
    median_similar = band[1] if band else None

    return {
        "predicted_price": predicted_price,
        "predicted_price_per_sqm": predicted_price / float(clean_payload["procedure_area"]),
        "similar_median_price": median_similar,
        "similar_count": similar_count,
        "advertised_area_used": clean_payload["advertised_area"],
        "similar_p25": band[0] if band else None,
        "similar_p75": band[2] if band else None,
        "model_vs_comparables": predicted_price / median_similar - 1 if median_similar else None,
        "asking_vs_model": asking_price / predicted_price - 1 if asking_price and predicted_price else None,
        "asking_price": asking_price,
        "comparable_scope": "Same area, type, subtype, rooms and registration; size within ±25%; 36 months ending in the selected month.",
        "reference_date": f"{clean_payload['year']}-{clean_payload['month']:02d}",
        "historical_mae": 240843.49,
    }


def roi(payload: dict[str, Any]) -> dict[str, Any]:
    basic = {key: payload[key] for key in ("purchase_price", "monthly_rent", "annual_costs", "closing_cost_rate", "vacancy_rate", "appreciation_rate")}
    result = calculate_roi(**basic)
    years = payload.get("holding_years", 5)
    selling_rate = payload.get("selling_cost_rate", .02)
    baseline = payload.get("model_value") or payload["purchase_price"]
    cost = result["acquisition_cost"]
    income = result["annual_net_income"]
    growth = payload["appreciation_rate"]

    def scenario(rate: float, duration: int) -> dict[str, Any]:
        future = baseline * (1 + rate) ** duration
        proceeds = future * (1 - selling_rate)
        profit = proceeds + income * duration - cost
        return {"year": duration, "growth_rate": rate, "future_value": future, "sale_proceeds": proceeds,
                "rental_income": income * duration, "net_profit": profit, "total_roi": profit / cost}

    result.update({
        "value_baseline": baseline,
        "projection": [scenario(growth, year) for year in range(years + 1)],
        "scenarios": [{"label": label, **scenario(rate, years)} for label, rate in
                      [("Lower growth", max(-.5, growth - .03)), ("Your assumption", growth), ("Higher growth", min(.5, growth + .03))]],
        "break_even_monthly_rent": payload["annual_costs"] / (12 * (1 - payload["vacancy_rate"])),
        "break_even_sale_price": max(0, (cost - income * years) / (1 - selling_rate)),
        "estimated_appreciation": baseline * growth,
        "one_year_roi": scenario(growth, 1)["total_roi"],
        "one_year_total_return": scenario(growth, 1)["net_profit"],
    })
    return result


def opportunities(
    years: list[int] | None = None,
    property_types: list[str] | None = None,
    areas: list[str] | None = None,
    min_transactions: int = 100,
    min_price: float = 0,
    max_price: float | None = None,
) -> list[dict[str, Any]]:
    summary = pd.DataFrame(area_summary(years, property_types, areas, min_transactions, min_price, max_price))
    if summary.empty:
        return []

    summary["activity_percentile"] = summary["transactions"].rank(pct=True) * 100
    summary["affordability_percentile"] = summary["median_price_per_sqm"].rank(pct=True, ascending=False) * 100
    summary["value_score"] = (summary.activity_percentile + summary.affordability_percentile) / 2
    summary = summary.sort_values("value_score", ascending=False)
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
