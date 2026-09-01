# Dubai ROI Analysis

Dubai real estate analytics project with notebook research, saved machine-learning models, and a Streamlit dashboard for market analysis, price prediction, and ROI calculations.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run Dashboard

```powershell
streamlit run app/streamlit_app.py
```

## Project Files

- `note.ipynb`: research notebook and model-development record
- `note.py`: reusable backend helpers exported from the notebook workflow
- `app/streamlit_app.py`: Streamlit dashboard
- `models/`: saved CatBoost and XGBoost models
- `figures/`: saved model-performance figures
- `data/`: local transaction data files
