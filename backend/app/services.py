from __future__ import annotations

import calendar
import os
import sqlite3
import urllib.request
from contextlib import closing
from functools import lru_cache
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


@lru_cache(maxsize=1)
def price_model():
    return load_price_model()


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


_market_lock = RLock()


def _market_data(*args) -> pd.DataFrame:
    # Concurrent overview/map requests must not read millions of rows twice on a cold cache.
    with _market_lock:
        return _market_data_cached(*args)


@lru_cache(maxsize=4)
def _market_data_cached(years: tuple, property_types: tuple, areas: tuple, min_price: float, max_price: float | None) -> pd.DataFrame:
    """Share the same bounded, read-only data snapshot across market endpoints."""
    where, params = _market_where(list(years), list(property_types), list(areas), min_price, max_price)
    dataset = _read_sql(
        f"SELECT instance_date, area_name_en, property_type_en, reg_type_en, actual_worth, procedure_area FROM transactions WHERE {where}", params
    )
    dataset["instance_date"] = pd.to_datetime(dataset["instance_date"], errors="coerce")
    dataset["price_per_sqm"] = dataset["actual_worth"] / dataset["procedure_area"]
    for column in ["area_name_en", "property_type_en", "reg_type_en"]:
        dataset[column] = dataset[column].astype("category")
    return dataset


def overview(
    years: list[int] | None = None,
    property_types: list[str] | None = None,
    areas: list[str] | None = None,
    min_price: float = 0,
    max_price: float | None = None,
) -> dict[str, Any]:
    dataset = _market_data(tuple(years or []), tuple(property_types or []), tuple(areas or []), min_price, max_price)
    if dataset.empty:
        return {"metrics": {"transactions": 0, "median_price": None, "median_area": None, "median_price_per_sqm": None}, "monthly": []}

    monthly = (
        dataset
        .dropna(subset=["instance_date", "actual_worth"])
        .assign(month_start=lambda df: df["instance_date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month_start", observed=True)
        .agg(transactions=("actual_worth", "size"), median_price=("actual_worth", "median"), median_price_per_sqm=("price_per_sqm", "median"))
        .reset_index()
        .sort_values("month_start")
    )

    annual = dataset.assign(year=dataset.instance_date.dt.year).groupby("year").agg(
        transactions=("actual_worth", "size"), median_price=("actual_worth", "median"), median_price_per_sqm=("price_per_sqm", "median")
    ).reset_index()
    mix = dataset.groupby("property_type_en", observed=True).agg(transactions=("actual_worth", "size"), median_price=("actual_worth", "median")).reset_index().sort_values("transactions", ascending=False)
    leaders = dataset.groupby("area_name_en", observed=True).size().sort_values(ascending=False)
    price_bands = pd.cut(dataset.actual_worth, [0, 500000, 1000000, 2000000, 5000000, float("inf")], labels=["Under AED 500k", "AED 500k–1m", "AED 1m–2m", "AED 2m–5m", "Over AED 5m"])
    off_plan = dataset.reg_type_en.eq("off-plan properties")
    dates = dataset.instance_date.dropna()
    return {
        "metrics": {
            "transactions": int(len(dataset)),
            "median_price": float(dataset["actual_worth"].median()),
            "median_area": float(dataset["procedure_area"].median()),
            "median_price_per_sqm": float(dataset["price_per_sqm"].median()),
            "total_value": float(dataset.actual_worth.sum()),
            "off_plan_share": float(off_plan.mean()),
            "under_1m_share": float(dataset.actual_worth.le(1000000).mean()),
            "price_p25": float(dataset.actual_worth.quantile(0.25)),
            "price_p75": float(dataset.actual_worth.quantile(0.75)),
            "top_5_share": float(leaders.head(5).sum() / len(dataset)),
            "leading_area": str(leaders.index[0]) if len(leaders) else None,
        },
        "coverage": {"start": dates.min().strftime("%Y-%m-%d"), "end": dates.max().strftime("%Y-%m-%d")} if len(dates) else None,
        "annual": _records(annual),
        "property_mix": _records(mix),
        "price_bands": [{"label": str(label), "transactions": int(count)} for label, count in price_bands.value_counts(sort=False).items()],
        "monthly": [
            {
                "month_start": row.month_start.strftime("%Y-%m-%d"),
                "transactions": int(row.transactions),
                "median_price": float(row.median_price),
                "median_price_per_sqm": float(row.median_price_per_sqm),
            }
            for row in monthly.itertuples()
        ],
    }


def area_summary(
    years: list[int] | None = None,
    property_types: list[str] | None = None,
    areas: list[str] | None = None,
    min_transactions: int = 25,
    min_price: float = 0,
    max_price: float | None = None,
) -> list[dict[str, Any]]:
    dataset = _market_data(tuple(years or []), tuple(property_types or []), tuple(areas or []), min_price, max_price)
    if dataset.empty:
        return []

    summary = (
        dataset
        .groupby("area_name_en", observed=True)
        .agg(
            transactions=("actual_worth", "size"),
            median_price=("actual_worth", "median"),
            mean_price=("actual_worth", "mean"),
            median_price_per_sqm=("price_per_sqm", "median"),
            median_area=("procedure_area", "median"),
            price_p25=("actual_worth", lambda values: values.quantile(0.25)),
            price_p75=("actual_worth", lambda values: values.quantile(0.75)),
            off_plan_share=("reg_type_en", lambda values: values.eq("off-plan properties").mean()),
        )
        .reset_index()
    )
    summary["market_share"] = summary.transactions / len(dataset)
    summary["price_vs_market"] = summary.median_price_per_sqm / dataset.price_per_sqm.median() - 1
    summary = summary[summary["transactions"].ge(min_transactions)]
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

    similar = _read_sql(
        """
        SELECT actual_worth, procedure_area, instance_date
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
    median_similar = None
    if len(similar) >= 10:
        median_similar = float(similar["actual_worth"].median())

    return {
        "predicted_price": predicted_price,
        "predicted_price_per_sqm": predicted_price / float(clean_payload["procedure_area"]),
        "similar_median_price": median_similar,
        "similar_count": int(len(similar)),
        "advertised_area_used": clean_payload["advertised_area"],
        "similar_p25": float(similar.actual_worth.quantile(.25)) if len(similar) >= 10 else None,
        "similar_p75": float(similar.actual_worth.quantile(.75)) if len(similar) >= 10 else None,
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
