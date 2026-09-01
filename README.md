# Dubai Real Estate ROI Analysis

An end-to-end Dubai real estate analytics project covering data cleaning, exploratory research, machine-learning model development, and an interactive Streamlit dashboard for market analysis, price prediction, and ROI planning.

The full research workflow is documented in `note.ipynb`. The notebook is written as the main analytical record for the project: it explains the dataset, cleaning decisions, feature selection, missing-value strategy, modeling experiments, validation results, and interpretation of the final outputs. The Streamlit app then turns that research into a usable dashboard.

## Project Objective

The goal of this project is to build a practical decision-support tool for Dubai real estate analysis. The project starts from raw transaction data, cleans and standardizes it, models missing room information, predicts property transaction value, and exposes the results through a dashboard that can support future ROI calculations.

The dashboard is designed around six views:

- Market Overview
- Area Comparison
- Price Prediction
- ROI Calculator
- Investment Opportunities
- Model Performance

## Research Summary

The research process follows a structured data-science workflow.

First, raw transaction files from Dubai real estate open-data sources are loaded and standardized into a consistent schema. The newer transaction file uses different column names from the older file, so the notebook maps both into shared fields such as `instance_date`, `procedure_name_en`, `property_type_en`, `property_sub_type_en`, `area_name_en`, `rooms_en`, `procedure_area`, `actual_worth`, and `meter_sale_price`.

Second, the project performs exploratory data analysis. This includes checking data types, missing values, categorical distributions, numerical distributions, transaction groups, room categories, area names, and price behavior. The analysis shows that the raw dataset contains multiple transaction types that should not be modeled together. Sales, mortgages, gifts, land transactions, and non-residential records behave differently, so the price-modeling dataset is narrowed to residential sales records.

Third, the project handles missing room values. Since `rooms_en` is an important predictor for property value, missing room categories are not ignored blindly. A CatBoost multiclass classifier is trained to infer missing room categories from property and location features. Predictions are accepted only when confidence is high enough, while low-confidence room predictions are left missing and later removed from the price-model dataset. This keeps the model useful without pretending uncertain imputations are ground truth.

Fourth, an XGBoost price model is trained to predict `actual_worth`, the registered transaction value. The model predicts `log_actual_worth` instead of raw price because real estate prices are strongly right-skewed. Predictions are converted back into AED using `np.expm1`.

Finally, the research outputs are turned into a dashboard. Heavy data cleaning is moved into reusable backend code and cached locally, so the dashboard can load prepared data faster instead of re-processing the full raw CSV every time.

## General Findings

Dubai real estate values are highly segmented by location, property area, property subtype, room category, and registration type. The strongest patterns in the analysis are not driven by one single feature. Instead, price behavior comes from the interaction between where the property is, what type of property it is, how large it is, whether it is off-plan or existing, and what room category it belongs to.

The dataset also shows why filtering matters. A raw real estate transaction dataset contains many valid records that are not comparable for a residential price model. Land, building, agricultural, gift, mortgage, and unusual procedure records can distort the relationship between property characteristics and sale value. The final model therefore focuses on residential sales records, which makes the results more interpretable for a dashboard user trying to estimate property value and ROI.

Area remains one of the most important business variables. In Dubai, the same room count and property size can imply very different values depending on whether the property is in a prime, waterfront, central, suburban, or developing area. This is why the dashboard includes both market-wide summaries and area-level comparisons.

Property size also matters strongly, but not in a perfectly linear way. Larger properties generally sell for higher total values, but price per square metre varies heavily across areas and property types. This is why the model uses total property area while the dashboard also reports price-per-square-metre statistics separately.

## Machine Learning

### Room Classification Model

The first model predicts missing `rooms_en` values.

Model type:

- CatBoost multiclass classifier

Target:

- `rooms_en`

Main features:

- Procedure name
- Property type
- Property usage
- Registration type
- Area
- Parking availability
- Property area
- Advertised area
- Time features

Final holdout performance:

- Accuracy: `0.9033`
- Macro F1: `0.6766`
- Weighted F1: `0.9030`

The room model performs strongly on common classes such as studio, 1 B/R, 2 B/R, and 3 B/R. Smaller rare classes such as penthouse and high bedroom counts are more difficult because they have far less support. This is expected in imbalanced real estate data.

### Price Prediction Model

The second model predicts property transaction value.

Model type:

- XGBoost regressor with native categorical handling

Target:

- `log_actual_worth`

Final prediction output:

- AED price prediction after inverse log transform

Main features:

- Procedure name
- Property type
- Property subtype
- Property usage
- Registration type
- Area
- Rooms
- Parking availability
- Property area
- Advertised area
- Year
- Month

Final test performance:

- MAE: `240,843.49 AED`
- RMSE: `598,296.59 AED`
- R2: `0.8892`

The validation and final test results are close, which suggests the model generalizes reasonably well instead of simply memorizing the training data. The training curve in `figures/xgboost_training_validation_rmse.png` also shows training and validation RMSE moving closely together across boosting rounds.

For ROI use, MAE is especially important because it gives a practical average error in AED. RMSE is also important because large price mistakes can materially change an investment decision.

## Dashboard

The Streamlit dashboard uses the cleaned dataset and saved models to provide an interactive interface.

### Market Overview

Shows transaction volume, median price, median area, median price per square metre, monthly trends, top areas by activity, and an area map.

### Area Comparison

Compares Dubai areas by transaction count, median price, median price per square metre, and median property area. This section helps identify how pricing differs across locations.

### Price Prediction

Allows users to input property characteristics and receive a predicted transaction price. The app filters prediction inputs to categories stored in the saved XGBoost model, which prevents unsupported category errors during prediction.

### ROI Calculator

Uses purchase price, rent expectations, operating costs, vacancy assumptions, closing costs, and appreciation assumptions to estimate gross yield, net yield, annual net income, and one-year ROI.

### Investment Opportunities

Ranks areas using a simple opportunity score based on market activity and median price per square metre. This is not investment advice, but it provides a starting point for comparing active areas.

### Model Performance

Displays the saved XGBoost training-versus-validation RMSE curve and summarizes how the model was evaluated.

## Performance Design

The raw dataset is large, so the dashboard avoids rebuilding the full cleaned DataFrame on every launch.

The backend can build local prepared files:

- `data/dashboard_cache.parquet`
- `data/dashboard.sqlite`

These files are generated locally and ignored by Git. The dashboard reads from the prepared cache when available, which makes normal use much faster than repeatedly parsing and cleaning the full raw CSV.

The saved ML models are stored in `models/`, so the dashboard can make predictions without retraining.

## Project Structure

```text
ROIProject/
├── app/
│   └── streamlit_app.py
├── data/
│   ├── dubai_area_alias_mapping.csv
│   ├── transactions-2026-07-10.csv
│   ├── Transactions.csv
│   ├── dashboard_cache.parquet
│   └── dashboard.sqlite
├── figures/
│   └── xgboost_training_validation_rmse.png
├── models/
│   ├── rooms_en_production_final_model.cbm
│   ├── rooms_en_validation_model.cbm
│   └── xgboost_price_model.json
├── note.ipynb
├── note.py
├── requirements.txt
└── README.md
```

Some local files are intentionally ignored because they are large or generated:

- Raw large CSV files
- Dashboard cache/database files
- Virtual environments
- Python cache files

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Run The Dashboard

```powershell
python -m streamlit run app/streamlit_app.py
```

If the default Streamlit port is already being used:

```powershell
python -m streamlit run app/streamlit_app.py --server.port 8503
```

## Rebuild The Dashboard Cache

The dashboard cache is built automatically if it does not exist. To force a rebuild:

```powershell
python -c "from note import prepare_dashboard_data; prepare_dashboard_data(force_rebuild=True)"
```

## Research Notebook

Use `note.ipynb` to review the complete research process. The notebook contains the detailed explanation for:

- Data loading and schema standardization
- Data-quality checks
- Feature classification
- Missing-value review
- Residential sales filtering
- Outlier handling
- Room imputation with CatBoost
- Price prediction with XGBoost
- Model evaluation
- Feature importance
- Dashboard preparation

## Important Limitations

This project is an analytical and educational tool. It should not be treated as financial advice.

The price model estimates transaction value from historical patterns. It does not know property condition, exact building quality, view, floor level, developer reputation, renovation quality, negotiation context, financing terms, or live market sentiment unless those variables are included in the data.

ROI calculations depend heavily on user assumptions for rent, vacancy, annual costs, fees, and appreciation. The dashboard is most useful as a scenario-testing tool, not as a guarantee of returns.

## Future Improvements

Useful next steps include:

- Add a real geospatial area lookup instead of approximate built-in map coordinates.
- Move dashboard queries fully into SQL for faster filtered aggregation.
- Add rental data so ROI can estimate rent automatically rather than requiring manual input.
- Add confidence intervals or prediction ranges around price estimates.
- Add model drift checks when new transaction data is added.
- Package the Streamlit app for cloud deployment.
- Add a clean API layer if the project later moves from Streamlit to React plus FastAPI.
