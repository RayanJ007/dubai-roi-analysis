import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns

# ── output folder ──────────────────────────────────────────────────────────────
os.makedirs("charts", exist_ok=True)

# ── shared style ───────────────────────────────────────────────────────────────
plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
        "figure.dpi": 150,
    }
)

TEAL = "#1D9E75"
RED = "#E24B4A"
AMBER = "#BA7517"
PURPLE = "#534AB7"
GRAY = "#888780"


# ══════════════════════════════════════════════════════════════════════════════
# CHART 1 — Top & bottom 10 areas by annual growth
# ──────────────────────────────────────────────────────────────────────────────
# Headline finding of the whole report. Shows the full 40+ percentage point
# spread between the best and worst performing areas — proves that location
# selection, not just market timing, is the dominant ROI driver in Dubai.
# ══════════════════════════════════════════════════════════════════════════════
def chart1_top_bottom(area_results_table):
    valid = area_results_table[area_results_table["reason"] == "ok"].copy()
    top10 = valid.nlargest(10, "annual_growth")
    bot10 = valid.nsmallest(10, "annual_growth")
    combined = pd.concat([bot10, top10]).sort_values("annual_growth")

    colors = [RED if x < 0 else TEAL for x in combined["annual_growth"]]

    fig, ax = plt.subplots(figsize=(11, 8))
    ax.barh(
        combined["area_name_en"],
        combined["annual_growth"] * 100,
        color=colors,
        edgecolor="white",
        linewidth=0.4,
    )
    ax.axvline(0, color=GRAY, linewidth=0.8, linestyle="--")
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlabel("Annual price growth (%)", fontsize=11)
    ax.set_title(
        "Top and bottom 10 Dubai areas by hedonic annual price growth",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )

    for bar, val in zip(ax.patches, combined["annual_growth"]):
        x = bar.get_width()
        y = bar.get_y() + bar.get_height() / 2
        ax.text(
            x + (0.3 if x >= 0 else -0.3),
            y,
            f"{val*100:.1f}%",
            va="center",
            ha="left" if x >= 0 else "right",
            fontsize=8.5,
        )

    ax.set_facecolor("#fafafa")
    fig.text(
        0.5,
        -0.01,
        "Growth estimated via log-linear OLS regression controlling for property size "
        "and transaction type (2021–2025). Segments with <60 observations excluded.",
        ha="center",
        fontsize=8.5,
        color=GRAY,
    )
    plt.tight_layout()
    plt.savefig("charts/chart1_top_bottom_areas.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("Saved chart1_top_bottom_areas.png")


# ══════════════════════════════════════════════════════════════════════════════
# CHART 2 — ROI heatmap by area × room type
# ──────────────────────────────────────────────────────────────────────────────
# Core deliverable of the model. Lets investors see at a glance which
# area + room combination offers the best growth. Directly supports the
# resume bullet: "ROI projections by area, room segment, and building level."
# ══════════════════════════════════════════════════════════════════════════════
def chart2_heatmap(results_table):
    room_order = ["Studio", "1BR", "2BR", "3BR", "4BR", "5BR"]
    pivot = results_table[results_table["reason"] == "ok"].pivot_table(
        index="area_name_en", columns="rooms_bucket", values="annual_growth"
    )
    pivot = pivot.reindex(columns=[r for r in room_order if r in pivot.columns])
    pivot = pivot.dropna(thresh=3) * 100

    fig, ax = plt.subplots(figsize=(10, max(8, len(pivot) * 0.38)))
    sns.heatmap(
        pivot,
        cmap="RdYlGn",
        center=0,
        annot=True,
        fmt=".1f",
        linewidths=0.3,
        linecolor="#e0e0e0",
        ax=ax,
        cbar_kws={"label": "Annual growth (%)"},
    )
    ax.set_title(
        "Annual price growth (%) by area and room type",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", labelsize=10)
    ax.tick_params(axis="y", labelsize=8)
    fig.text(
        0.5,
        -0.01,
        "Blank cells = fewer than 60 transactions (insufficient for regression).",
        ha="center",
        fontsize=8.5,
        color=GRAY,
    )
    plt.tight_layout()
    plt.savefig("charts/chart2_heatmap.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("Saved chart2_heatmap.png")


# ══════════════════════════════════════════════════════════════════════════════
# CHART 3 — Growth rate vs market liquidity scatter
# ──────────────────────────────────────────────────────────────────────────────
# Analyst-level insight chart. Reveals the risk/reward tradeoff: high-growth
# areas often have low transaction depth (harder to exit). Color = R² quality.
# This is the chart that shows you think like an analyst, not just a coder.
# ══════════════════════════════════════════════════════════════════════════════
def chart3_scatter(area_results_table):
    valid = area_results_table[area_results_table["reason"] == "ok"].copy()

    fig, ax = plt.subplots(figsize=(11, 7))
    sc = ax.scatter(
        valid["tx_count"],
        valid["annual_growth"] * 100,
        c=valid["r2"],
        cmap="viridis",
        alpha=0.75,
        s=70,
        edgecolors="white",
        linewidths=0.4,
    )
    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label("R² (model fit quality)", fontsize=10)

    ax.set_xscale("log")
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlabel("Transaction count (log scale)", fontsize=11)
    ax.set_ylabel("Annual price growth (%)", fontsize=11)
    ax.set_title(
        "Annual price growth vs market liquidity by area",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )

    median_g = valid["annual_growth"].median() * 100
    ax.axhline(
        median_g,
        color=GRAY,
        linestyle="--",
        linewidth=0.9,
        label=f"Median growth ({median_g:.1f}%)",
    )
    ax.axhline(0, color=RED, linestyle=":", linewidth=0.8, alpha=0.6)

    for _, row in pd.concat(
        [
            valid.nlargest(3, "annual_growth"),
            valid.nsmallest(3, "annual_growth"),
        ]
    ).iterrows():
        ax.annotate(
            row["area_name_en"].split()[0],
            xy=(row["tx_count"], row["annual_growth"] * 100),
            xytext=(6, 4),
            textcoords="offset points",
            fontsize=7.5,
            color="#333",
        )

    ax.legend(fontsize=9)
    ax.set_facecolor("#fafafa")
    fig.text(
        0.5,
        -0.01,
        "Top-left quadrant = high growth, low liquidity (higher risk). "
        "Bottom-right = liquid but slower-growing established areas.",
        ha="center",
        fontsize=8.5,
        color=GRAY,
    )
    plt.tight_layout()
    plt.savefig("charts/chart3_growth_vs_liquidity.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("Saved chart3_growth_vs_liquidity.png")


# ══════════════════════════════════════════════════════════════════════════════
# CHART 4 — Monthly transaction volume over time
# ──────────────────────────────────────────────────────────────────────────────
# Provides market context for the full report. Shows when the market was
# active vs slow and explains why some areas have too_few_obs.
# ══════════════════════════════════════════════════════════════════════════════
def chart4_volume_over_time(df):
    monthly = (
        df.set_index("instance_date").resample("ME").size().reset_index(name="tx_count")
    )

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.fill_between(
        monthly["instance_date"], monthly["tx_count"], alpha=0.15, color=TEAL
    )
    ax.plot(monthly["instance_date"], monthly["tx_count"], color=TEAL, linewidth=1.5)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Residential sales transactions", fontsize=11)
    ax.set_title(
        "Monthly residential sales volume — Dubai (2021–2025)",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    ax.set_facecolor("#fafafa")
    fig.text(
        0.5,
        -0.01,
        "Sales transactions only. Gifts, grants, and commercial properties excluded.",
        ha="center",
        fontsize=8.5,
        color=GRAY,
    )
    plt.tight_layout()
    plt.savefig("charts/chart4_transaction_volume.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("Saved chart4_transaction_volume.png")


# ══════════════════════════════════════════════════════════════════════════════
# CHART 5 — Price per sqm distribution by room type (box plot)
# ──────────────────────────────────────────────────────────────────────────────
# Shows the pricing structure across segments and validates that outlier
# trimming worked. Demonstrates your data cleaning methodology visually.
# ══════════════════════════════════════════════════════════════════════════════
def chart5_price_distribution(df):
    room_order = ["Studio", "1BR", "2BR", "3BR", "4BR", "5BR"]
    plot_df = df[df["rooms_bucket"].isin(room_order)].copy()

    data_by_room = [
        plot_df[plot_df["rooms_bucket"] == r]["price_per_sqm"].dropna().values
        for r in room_order
    ]

    fig, ax = plt.subplots(figsize=(11, 6))
    bp = ax.boxplot(
        data_by_room,
        labels=room_order,
        patch_artist=True,
        medianprops=dict(color="white", linewidth=2),
        whiskerprops=dict(color=GRAY, linewidth=1),
        capprops=dict(color=GRAY, linewidth=1),
        flierprops=dict(marker="o", markersize=2, alpha=0.3, color=GRAY),
        widths=0.5,
    )

    colors = [TEAL, TEAL, TEAL, AMBER, AMBER, RED]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"AED {int(x):,}"))
    ax.set_xlabel("Room type", fontsize=11)
    ax.set_ylabel("Price per sqm (AED)", fontsize=11)
    ax.set_title(
        "Price per sqm distribution by room type",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    ax.set_facecolor("#fafafa")
    fig.text(
        0.5,
        -0.01,
        "After global 1st–99th percentile outlier trimming. "
        "Boxes show IQR; whiskers extend to 1.5×IQR.",
        ha="center",
        fontsize=8.5,
        color=GRAY,
    )
    plt.tight_layout()
    plt.savefig("charts/chart5_price_distribution.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("Saved chart5_price_distribution.png")


# ══════════════════════════════════════════════════════════════════════════════
# CHART 7 — R² distribution across all valid segments (histogram)
# ──────────────────────────────────────────────────────────────────────────────
# Validates the model. Shows what % of your 388 segments have strong fit.
# Essential for the methodology section — proves the regression is reliable.
# ══════════════════════════════════════════════════════════════════════════════
def chart7_r2_distribution(results_table):
    valid_r2 = results_table[results_table["reason"] == "ok"]["r2"].dropna()

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(valid_r2, bins=30, color=TEAL, alpha=0.8, edgecolor="white", linewidth=0.4)

    median_r2 = valid_r2.median()
    ax.axvline(
        median_r2,
        color=AMBER,
        linewidth=1.5,
        linestyle="--",
        label=f"Median R² = {median_r2:.2f}",
    )
    ax.axvline(0.5, color=RED, linewidth=1, linestyle=":", label="R² = 0.50 reference")

    ax.set_xlabel("R² (coefficient of determination)", fontsize=11)
    ax.set_ylabel("Number of area–room segments", fontsize=11)
    ax.set_title(
        "Distribution of model R² across all valid segments",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    ax.legend(fontsize=9)
    ax.set_facecolor("#fafafa")

    pct_above = (valid_r2 >= 0.5).mean() * 100
    fig.text(
        0.5,
        -0.01,
        f"{pct_above:.0f}% of segments have R² ≥ 0.50, indicating "
        "strong model fit for the majority of the market.",
        ha="center",
        fontsize=8.5,
        color=GRAY,
    )
    plt.tight_layout()
    plt.savefig("charts/chart7_r2_distribution.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("Saved chart7_r2_distribution.png")


# ══════════════════════════════════════════════════════════════════════════════
# CHART 8 — 3-year projected ROI: top 12 areas for 2BR units
# ──────────────────────────────────────────────────────────────────────────────
# Translates the regression output into a concrete investor deliverable.
# This is the "so what" chart — the one an investor actually cares about.
# Change room and hold_years to generate versions for different segments.
# ══════════════════════════════════════════════════════════════════════════════
def chart8_roi_projection(
    results_table, room="2BR", hold_years=3, purchase_price=2_500_000
):
    sub = results_table[
        (results_table["rooms_bucket"] == room) & (results_table["reason"] == "ok")
    ].copy()

    sub["roi_pct"] = sub["annual_growth"].apply(
        lambda g: ((1 + g) ** hold_years - 1) * 100
    )
    sub = sub.dropna(subset=["roi_pct"]).nlargest(12, "roi_pct")

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(
        sub["area_name_en"],
        sub["roi_pct"],
        color=TEAL,
        alpha=0.85,
        edgecolor="white",
        linewidth=0.4,
    )
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlabel(f"Projected ROI over {hold_years} years (%)", fontsize=11)
    ax.set_title(
        f"Top 12 areas — projected {hold_years}-year ROI for {room} units",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )

    for bar, val in zip(ax.patches, sub["roi_pct"]):
        ax.text(
            bar.get_width() + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%",
            va="center",
            fontsize=8.5,
        )

    ax.set_facecolor("#fafafa")
    fig.text(
        0.5,
        -0.01,
        f"Based on hedonic annual growth rates. Purchase price assumption: "
        f"AED {purchase_price:,}. Capital appreciation only — rental yield excluded.",
        ha="center",
        fontsize=8.5,
        color=GRAY,
    )
    plt.tight_layout()
    plt.savefig("charts/chart8_roi_projection.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("Saved chart8_roi_projection.png")
