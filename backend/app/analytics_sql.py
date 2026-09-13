"""Exact analytics with disk-backed SQLite sorting, never transaction DataFrames."""
from __future__ import annotations

import sqlite3
from itertools import groupby

import numpy as np

NUMERIC_BUFFER_BYTES = 32 * 1024 * 1024


def _disk_quantiles(connection: sqlite3.Connection, source: str, column: str,
              group: str = "'all'", probabilities: tuple = (.25, .5, .75)) -> dict:
    """Linear interpolation, identical to pandas' default quantile definition.

    SQL identifiers/expressions are internal constants, never request values.
    Only the two order statistics surrounding each quantile leave SQLite.
    temp_store=FILE keeps large window-function sorts off the Python heap.
    """
    selections = []
    for index, p in enumerate(probabilities):
        position = f"((n - 1) * {float(p)})"
        lower = f"CAST({position} AS INTEGER)"
        # At integral positions lo == hi; COALESCE also covers singleton groups.
        lo = f"MAX(CASE WHEN r = {lower} THEN v END)"
        hi = f"MAX(CASE WHEN r = {lower} + 1 THEN v END)"
        selections.append(f"{lo} + (COALESCE({hi}, {lo}) - {lo}) * ({position} - {lower}) AS q{index}")
    rows = connection.execute(f"""
        WITH ranked AS (
            SELECT {group} AS g, {column} AS v,
                   ROW_NUMBER() OVER (PARTITION BY {group} ORDER BY {column}) - 1 AS r,
                   COUNT(*) OVER (PARTITION BY {group}) AS n
            FROM {source} WHERE {column} IS NOT NULL AND {group} IS NOT NULL
        )
        SELECT g, {', '.join(selections)} FROM ranked GROUP BY g
    """)
    return {row[0]: tuple(row[1:]) for row in rows}


def distributions(connection: sqlite3.Connection, source: str, columns: tuple,
                  group: str = "'all'", probabilities: tuple = (.25, .5, .75)) -> dict:
    """Stream one group into an owned numeric buffer capped at 32 MiB.

    SQLite performs grouping on disk. NumPy partitions numbers in place, with
    the same exact interpolation as pandas. No transaction objects are cached.
    Very large groups fall back to disk order statistics rather than sampling.
    Callers supply non-null numeric columns; SQL expressions are internal only.
    """
    counts = dict(connection.execute(f"SELECT {group}, COUNT(*) FROM {source} "
                  f"WHERE {group} IS NOT NULL GROUP BY {group}"))
    if max(counts.values(), default=0) * len(columns) * 8 > NUMERIC_BUFFER_BYTES:
        by_column = [_disk_quantiles(connection, source, column, group, probabilities) for column in columns]
        return {key: tuple(values[key] for values in by_column) for key in counts}
    order = '' if group == "'all'" else f' ORDER BY {group}'
    cursor = connection.execute(f"SELECT {group}, {', '.join(columns)} FROM {source} "
                                f"WHERE {group} IS NOT NULL{order}")
    result = {}
    for key, rows in groupby(cursor, key=lambda row: row[0]):
        values = np.fromiter((value for row in rows for value in row[1:]), dtype=np.float64,
                             count=counts[key] * len(columns)).reshape(-1, len(columns))
        bands = np.quantile(values, probabilities, axis=0, overwrite_input=True)
        result[key] = tuple(tuple(float(value) for value in band) for band in bands.T)
        del values
    return result


def quantiles(connection: sqlite3.Connection, source: str, column: str,
              group: str = "'all'", probabilities: tuple = (.25, .5, .75)) -> dict:
    return {key: values[0] for key, values in distributions(connection, source, (column,), group, probabilities).items()}


def summarize(connection: sqlite3.Connection, where: str, params: list) -> tuple[dict, list]:
    # One filtered disk snapshot shared by the aggregates for this request.
    connection.execute(f"""CREATE TEMP TABLE market AS
        SELECT date(instance_date) AS day, strftime('%Y-%m-01', instance_date) AS month_start,
               CAST(strftime('%Y', instance_date) AS INTEGER) AS year,
               area_name_en, property_type_en, reg_type_en,
               actual_worth, procedure_area, 1.0 * actual_worth / procedure_area AS price_per_sqm
        FROM transactions WHERE {where}""", params)
    base = dict(connection.execute("""SELECT COUNT(*) AS transactions,
        SUM(actual_worth) AS total_value,
        AVG(CASE WHEN reg_type_en = 'off-plan properties' THEN 1.0 ELSE 0.0 END) AS off_plan_share,
        AVG(actual_worth <= 1000000) AS under_1m_share,
        MIN(day) AS start, MAX(day) AS end FROM market""").fetchone())
    count = base['transactions']
    if not count:
        return {"metrics": {"transactions": 0, "median_price": None, "median_area": None,
                            "median_price_per_sqm": None}, "monthly": []}, []

    prices, sizes, sqms = distributions(connection, 'market', ('actual_worth', 'procedure_area', 'price_per_sqm'))['all']
    size, sqm = sizes[1], sqms[1]
    area_rows = [dict(row) for row in connection.execute("""SELECT area_name_en,
        COUNT(*) AS transactions, AVG(actual_worth) AS mean_price,
        AVG(CASE WHEN reg_type_en = 'off-plan properties' THEN 1.0 ELSE 0.0 END) AS off_plan_share
        FROM market WHERE area_name_en IS NOT NULL GROUP BY area_name_en
        ORDER BY transactions DESC, area_name_en""")]
    area_values = distributions(connection, 'market', ('actual_worth', 'procedure_area', 'price_per_sqm'), 'area_name_en')
    for row in area_rows:
        price, size_band, sqm_band = area_values[row['area_name_en']]
        row.update(price_p25=price[0], median_price=price[1], price_p75=price[2],
                   median_area=size_band[1], median_price_per_sqm=sqm_band[1])
    for row in area_rows:
        row['market_share'] = row['transactions'] / count
        row['price_vs_market'] = row['median_price_per_sqm'] / sqm - 1

    metrics = {key: base[key] for key in ('transactions', 'total_value', 'off_plan_share', 'under_1m_share')}
    metrics.update(median_price=prices[1], median_area=size, median_price_per_sqm=sqm,
                   price_p25=prices[0], price_p75=prices[2],
                   top_5_share=sum(row['transactions'] for row in area_rows[:5]) / count,
                   leading_area=area_rows[0]['area_name_en'] if area_rows else None)
    result = {'metrics': metrics, 'coverage': {'start': base['start'], 'end': base['end']} if base['start'] else None}
    for group, output in [('month_start', 'monthly'), ('year', 'annual'), ('property_type_en', 'property_mix')]:
        rows = [dict(row) for row in connection.execute(f"""SELECT {group}, COUNT(*) AS transactions
            FROM market WHERE {group} IS NOT NULL GROUP BY {group} ORDER BY {group}""")]
        fields = [('actual_worth', 'median_price')]
        if output != 'property_mix':
            fields.append(('price_per_sqm', 'median_price_per_sqm'))
        values = distributions(connection, 'market', tuple(column for column, _ in fields), group, (.5,))
        for row in rows:
            for index, (_, name) in enumerate(fields):
                row[name] = values[row[group]][index][0]
        if output == 'property_mix':
            rows.sort(key=lambda row: -row['transactions'])
        result[output] = rows
    bands = list(connection.execute("""SELECT
        SUM(actual_worth <= 500000),
        SUM(actual_worth > 500000 AND actual_worth <= 1000000),
        SUM(actual_worth > 1000000 AND actual_worth <= 2000000),
        SUM(actual_worth > 2000000 AND actual_worth <= 5000000),
        SUM(actual_worth > 5000000) FROM market""").fetchone())
    result['price_bands'] = [dict(label=label, transactions=value) for label, value in zip(
        ['Under AED 500k', 'AED 500k–1m', 'AED 1m–2m', 'AED 2m–5m', 'Over AED 5m'], bands)]
    return result, area_rows
