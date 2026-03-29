import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ----------------------------
# CONFIG (edit these)
# ----------------------------
AREA_TARGET = "Dubai Marina"
ROOM_TARGET = "2BR"
PRICE_MIN_AED = 2_200_000
PRICE_MAX_AED = 3_000_000

START_DATE = pd.to_datetime("2021-01-01")
END_DATE = None

CHUNKSIZE = 200_000

# Hedonic regression window + minimum sample size per (area, room) segment
HEDONIC_YEARS_WINDOW = 5
MIN_OBS = 60

# Basic outlier trimming on price_per_sqm (global)
TRIM_PCT_LOW = 0.01
TRIM_PCT_HIGH = 0.99

# ----------------------------
# Load Data
# ----------------------------
print("Loading Transactions.csv ... (may take few min)")
chunks = pd.read_csv("data/Transactions.csv", chunksize=CHUNKSIZE, low_memory=False)

use_cols = [
    "instance_date",
    "area_name_en",
    "building_name_en",
    "rooms_en",
    "meter_sale_price",
    "actual_worth",
    "procedure_area",
    "trans_group_en",  # Sales / Gifts / Grants etc.
    "property_usage_en",  # Residential / Commercial etc.
    "reg_type_en",  # Off-Plan / Existing (wording may vary)
]

df_list = []
for c in chunks:
    c = c[use_cols].copy()
    df_list.append(c)

transactions = pd.concat(df_list, ignore_index=True)
print("Transactions loaded:", transactions.shape)

# ----------------------------
# Clean Data
# ----------------------------
df = transactions.copy()

df["instance_date"] = pd.to_datetime(
    df["instance_date"], dayfirst=True, errors="coerce"
)
df["procedure_area"] = pd.to_numeric(df["procedure_area"], errors="coerce")
df["actual_worth"] = pd.to_numeric(df["actual_worth"], errors="coerce")
df["meter_sale_price"] = pd.to_numeric(df["meter_sale_price"], errors="coerce")

# Drop invalid core fields
df = df.dropna(subset=["instance_date", "area_name_en", "procedure_area"])
df = df[df["procedure_area"] > 0]

# Construct price_per_sqm (prefer meter_sale_price; fallback to actual_worth/procedure_area)
df["price_per_sqm"] = df["meter_sale_price"]
missing_ppsqm = df["price_per_sqm"].isna() & df["actual_worth"].notna()
df.loc[missing_ppsqm, "price_per_sqm"] = (
    df.loc[missing_ppsqm, "actual_worth"] / df.loc[missing_ppsqm, "procedure_area"]
)

df = df.dropna(subset=["price_per_sqm"])
df = df[df["price_per_sqm"] > 0]

# Time filter
df = df[df["instance_date"] >= START_DATE]
if END_DATE is not None:
    df = df[df["instance_date"] <= END_DATE]

print("Data cleaned:", df.shape)


# ----------------------------
# Rooms normalization
# ----------------------------
def normalize_rooms(x):
    if pd.isna(x):
        return np.nan
    s = str(x).strip().lower()

    if s == "studio":
        return "Studio"
    if s == "1 b/r":
        return "1BR"
    if s == "single room":
        return "Single Room"
    if s == "2 b/r":
        return "2BR"
    if s == "3 b/r":
        return "3BR"
    if s == "4 b/r":
        return "4BR"
    if s == "5 b/r":
        return "5BR"
    if s == "6 b/r":
        return "6BR"
    if s == "7 b/r":
        return "7BR"
    if s == "8 b/r":
        return "8BR"
    if s == "9 b/r":
        return "9BR"
    if s == "10 b/r":
        return "10BR"
    if s == "penthouse":
        return "Penthouse"
    if s == "commercial":
        return "Commercial"
    return np.nan


df["rooms_bucket"] = df["rooms_en"].apply(normalize_rooms)
df = df.dropna(subset=["rooms_bucket"])
print("Room Buckets added:", df.shape)

# ----------------------------
# (1) Filter noise
# ----------------------------
# Transaction Type: keep Sales only
df["trans_group_en"] = df["trans_group_en"].astype(str)
df = df[df["trans_group_en"].str.strip().str.lower() == "sales"]

# Usage: Residential only
df["property_usage_en"] = df["property_usage_en"].astype(str)
df = df[df["property_usage_en"].str.strip().str.lower() == "residential"]

# reg_type_en must exist for hedonic control (drop missing)
df["reg_type_en"] = df["reg_type_en"].replace({None: np.nan})
df = df.dropna(subset=["reg_type_en"])

print("After Sales + Residential + reg_type filter:", df.shape)

# Filter out extreme price_per_sqm outliers (global trimming)
low_cut = df["price_per_sqm"].quantile(TRIM_PCT_LOW)
high_cut = df["price_per_sqm"].quantile(TRIM_PCT_HIGH)
df = df[(df["price_per_sqm"] >= low_cut) & (df["price_per_sqm"] <= high_cut)]
print("After global price_per_sqm trimming:", df.shape)

# ----------------------------
# Clean building_name_en for mapping / search
# ----------------------------
df["building_name_en"] = df["building_name_en"].astype(str).str.strip()
df.loc[
    df["building_name_en"].str.lower().isin(["nan", "none", ""]), "building_name_en"
] = np.nan


# ----------------------------
# BUILDING -> AREA dimension
# Each building gets the "most common" area_name_en (mode).
# Buildings with no area are excluded.
# ----------------------------
building_dim = (
    df.dropna(subset=["building_name_en", "area_name_en"])
    .groupby("building_name_en", as_index=False)["area_name_en"]
    .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan)
    .dropna(subset=["area_name_en"])
)

# Optional: sort for nicer dropdown/search experience
building_dim = building_dim.sort_values("building_name_en").reset_index(drop=True)

print("Building dimension rows:", len(building_dim))


# ----------------------------
# Hedonic log-linear regression per (area, rooms_bucket)
# ln(price_per_sqm) = alpha + beta_time*(years) + beta_reg*(reg_type dummies) + beta_area*(log(procedure_area)) + eps
# ----------------------------
def hedonic_growth_log_linear(
    g: pd.DataFrame,
    years_window: int = 5,
    min_obs: int = 200,
):
    cols_needed = ["instance_date", "price_per_sqm", "procedure_area", "reg_type_en"]
    d = g[cols_needed].copy()

    # convert types to correct data types
    d["instance_date"] = pd.to_datetime(d["instance_date"], errors="coerce")
    d["price_per_sqm"] = pd.to_numeric(d["price_per_sqm"], errors="coerce")
    d["procedure_area"] = pd.to_numeric(d["procedure_area"], errors="coerce")

    # Drop unusable rows
    d = d.dropna(
        subset=["instance_date", "price_per_sqm", "procedure_area", "reg_type_en"]
    )
    d = d[(d["price_per_sqm"] > 0) & (d["procedure_area"] > 0)]

    if d.empty:
        return pd.Series(
            {
                "annual_growth": np.nan,
                "tx_count": 0,
                "r2": np.nan,
                "beta_time": np.nan,
                "alpha": np.nan,
                "reason": "no_data",
            }
        )

    # last N years window relative to the segment’s last date
    last_date = d["instance_date"].max()
    cutoff = last_date - pd.DateOffset(years=years_window)
    d = d[d["instance_date"] >= cutoff].copy()

    # require minimum number of observations for regression validity (can be tuned)
    n = len(d)
    if n < min_obs:
        return pd.Series(
            {
                "annual_growth": np.nan,
                "tx_count": int(n),
                "r2": np.nan,
                "beta_time": np.nan,
                "alpha": np.nan,
                "reason": "too_few_obs",
            }
        )

    d = d.sort_values("instance_date")

    # y = ln(price_per_sqm)
    y = np.log(d["price_per_sqm"].to_numpy())

    # time in years since first obs in this window
    x_time = (
        (d["instance_date"] - d["instance_date"].min()).dt.days / 365.25
    ).to_numpy()

    # control: size-efficiency (log area)
    x_area = np.log(d["procedure_area"].to_numpy())

    # control: reg_type categorical -> dummies
    reg_dum = pd.get_dummies(
        d["reg_type_en"].astype(str).str.strip(), prefix="reg", drop_first=True
    )

    # Build design matrix with intercept
    X_parts = [
        pd.Series(1.0, index=d.index, name="const"),
        pd.Series(x_time, index=d.index, name="time_years"),
        pd.Series(x_area, index=d.index, name="log_area"),
        reg_dum,
    ]
    X_df = pd.concat(X_parts, axis=1)

    X = X_df.to_numpy(dtype=float)

    # Check for zero variance in time (cannot estimate growth if no time variation)
    if np.nanvar(x_time) == 0:
        return pd.Series(
            {
                "annual_growth": np.nan,
                "tx_count": int(n),
                "r2": np.nan,
                "beta_time": np.nan,
                "alpha": np.nan,
                "reason": "no_time_variation",
            }
        )

    # OLS via least squares (no extra libs)
    try:
        beta, residuals, rank, svals = np.linalg.lstsq(X, y, rcond=None)
    except Exception:
        return pd.Series(
            {
                "annual_growth": np.nan,
                "tx_count": int(n),
                "r2": np.nan,
                "beta_time": np.nan,
                "alpha": np.nan,
                "reason": "lstsq_failed",
            }
        )

    y_hat = X @ beta  # dot product to get fitted values
    ss_res = float(np.sum((y - y_hat) ** 2))  # residual sum of squares
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))  # total sum of squares
    r2 = np.nan if ss_tot == 0 else 1.0 - ss_res / ss_tot  # R-squared calculation

    # Extract coefficients
    coef_names = list(
        X_df.columns
    )  # get names from design matrix (const, time_years, log_area, reg dummies)
    beta_map = dict(
        zip(coef_names, beta)
    )  # map coefficient names to values for easy access

    alpha = float(beta_map.get("const", np.nan))  # intercept (base log price_per_sqm)
    beta_time = float(
        beta_map.get("time_years", np.nan)
    )  # time coefficient (log price_per_sqm growth per year)

    # Pure annual growth implied by beta_time (since x_time is in years)
    annual_growth = float(np.exp(beta_time) - 1.0)

    return pd.Series(
        {
            "annual_growth": annual_growth,
            "tx_count": int(n),
            "r2": float(r2),
            "beta_time": beta_time,
            "alpha": alpha,
            "reason": "ok",
        }
    )


# ----------------------------
# Run across all (area, rooms_bucket)
# ----------------------------
results_table = (
    df.groupby(["area_name_en", "rooms_bucket"], sort=False)
    .apply(
        lambda g: hedonic_growth_log_linear(
            g, years_window=HEDONIC_YEARS_WINDOW, min_obs=MIN_OBS
        )
    )
    .reset_index()
)

print("NaNs in annual_growth:", results_table["annual_growth"].isna().sum())

with pd.option_context(
    "display.max_rows",
    None,
    "display.max_columns",
    None,
    "display.width",
    None,
    "display.max_colwidth",
    None,
):
    print(results_table.sort_values(["area_name_en", "rooms_bucket"]))

# -----------------------------------
# AREA-LEVEL GROWTH (no room bucket)
# -----------------------------------

area_results_table = (
    df.groupby(["area_name_en"], sort=False)
    .apply(
        lambda g: hedonic_growth_log_linear(
            g, years_window=HEDONIC_YEARS_WINDOW, min_obs=MIN_OBS
        )
    )
    .reset_index()
)

# -----------------------------------
# SAFETY: Remove unrealistic growth
# If annual_growth > 1 (100%), mark as NaN
# -----------------------------------
mask_unrealistic = area_results_table["annual_growth"] > 1

area_results_table.loc[mask_unrealistic, ["annual_growth", "beta_time", "r2"]] = np.nan

area_results_table.loc[mask_unrealistic, "reason"] = "growth_gt_100pct"

print("\nArea-Level Growth Results")
with pd.option_context(
    "display.max_rows",
    None,
    "display.max_columns",
    None,
    "display.width",
    None,
    "display.max_colwidth",
    None,
):
    print(area_results_table.sort_values("area_name_en"))

# -----------------------------------
# BUILDING -> AREA MAPPING TABLE
# -----------------------------------

# Clean building names
df["building_name_en"] = df["building_name_en"].astype(str).str.strip()

df.loc[
    df["building_name_en"].str.lower().isin(["nan", "none", ""]), "building_name_en"
] = np.nan

# Create mapping
building_area_table = (
    df.dropna(subset=["building_name_en", "area_name_en"])
    .groupby("building_name_en", as_index=False)["area_name_en"]
    .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan)
    .dropna(subset=["area_name_en"])
    .sort_values("building_name_en")
    .reset_index(drop=True)
)


def calculate_roi(purchase_price, annual_growth, hold_years):
    future_value = purchase_price * (1 + annual_growth) ** hold_years
    roi = (future_value - purchase_price) / purchase_price
    return future_value, roi


# -----------------------------------
# ROI HELPERS (paste after calculate_roi)
# -----------------------------------
def roi_area_room(area_name, room_bucket, purchase_price, hold_years, results_table):

    m = (results_table["area_name_en"] == area_name) & (
        results_table["rooms_bucket"] == room_bucket
    )

    if not m.any():
        return "no_match"

    g = results_table.loc[m, "annual_growth"].iloc[0]

    if pd.isna(g):
        return results_table.loc[m, "reason"].iloc[0]

    _, roi = calculate_roi(purchase_price, g, hold_years)

    return round(roi * 100, 2)  # returns % only


def roi_area(area_name, purchase_price, hold_years, area_results_table):

    m = area_results_table["area_name_en"] == area_name

    if not m.any():
        return "no_match"

    g = area_results_table.loc[m, "annual_growth"].iloc[0]

    if pd.isna(g):
        return area_results_table.loc[m, "reason"].iloc[0]

    _, roi = calculate_roi(purchase_price, g, hold_years)

    return round(roi * 100, 2)


def roi_building_room(
    building_name,
    room_bucket,
    purchase_price,
    hold_years,
    building_area_table,
    results_table,
):

    m1 = building_area_table["building_name_en"] == building_name

    if not m1.any():
        return "building_not_found"

    area_name = building_area_table.loc[m1, "area_name_en"].iloc[0]

    m2 = (results_table["area_name_en"] == area_name) & (
        results_table["rooms_bucket"] == room_bucket
    )

    if not m2.any():
        return "area_room_not_found"

    g = results_table.loc[m2, "annual_growth"].iloc[0]

    if pd.isna(g):
        return results_table.loc[m2, "reason"].iloc[0]

    _, roi = calculate_roi(purchase_price, g, hold_years)

    return round(roi * 100, 2)


print(roi_area_room("Al Hebiah Fourth", "2BR", 2_500_000, 3, results_table))

print(roi_area("Al Hebiah Fourth", 2_500_000, 3, area_results_table))

print(
    roi_building_room(
        "OLYMPIC PARK 1", "2BR", 2_500_000, 3, building_area_table, results_table
    )
)


# -----------------------------------------
# FULL ALPHABETICAL AREA LIST
# -----------------------------------------

all_areas = df["area_name_en"].dropna().unique()

all_areas_sorted = sorted(all_areas)

area_table = pd.DataFrame({"area_name_en": all_areas_sorted})

print("\n=== FULL AREA LIST (ALPHABETICAL) ===")
print(area_table.to_string(index=False))

from dubai_charts import *

# ══════════════════════════════════════════════════════════════════════════════
# RUN ALL
# ──────────────────────────────────────────────────────────────────────────────
# Paste this at the bottom of your main analysis script, or import and call
# each function individually after your pipeline has run.
#
# Required variables already in memory from your main script:
#   results_table       — area x room level regression output
#   area_results_table  — area level regression output
#   df                  — cleaned transactions dataframe
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    chart1_top_bottom(area_results_table)
    chart2_heatmap(results_table)
    chart3_scatter(area_results_table)
    chart4_volume_over_time(df)
    chart5_price_distribution(df)
    chart6_offplan_vs_existing(df, area_results_table)
    chart7_r2_distribution(results_table)
    chart8_roi_projection(results_table)

    print("\nAll 8 charts saved to charts/")
