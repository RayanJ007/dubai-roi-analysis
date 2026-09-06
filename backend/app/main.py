from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import services
from .schemas import PricePredictionRequest, RoiRequest


PROJECT_ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(
    title="Dubai Real Estate ROI API",
    description="FastAPI backend for market analytics, price prediction, and ROI calculations.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

figures_dir = PROJECT_ROOT / "figures"
if figures_dir.exists():
    app.mount("/figures", StaticFiles(directory=figures_dir), name="figures")


def parse_csv(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    parsed: list[str] = []
    for value in values:
        parsed.extend([part.strip() for part in value.split(",") if part.strip()])
    return parsed or None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/options")
def get_options():
    return services.options()


@app.get("/market/overview")
def get_market_overview(
    years: Annotated[list[int] | None, Query()] = None,
    property_types: Annotated[list[str] | None, Query()] = None,
    areas: Annotated[list[str] | None, Query()] = None,
    min_transactions: int | None = None,
    min_price: float = Query(default=0, ge=0),
    max_price: float | None = Query(default=None, gt=0),
):
    return services.overview(years, parse_csv(property_types), parse_csv(areas), min_price, max_price)


@app.get("/market/areas")
def get_area_summary(
    years: Annotated[list[int] | None, Query()] = None,
    property_types: Annotated[list[str] | None, Query()] = None,
    areas: Annotated[list[str] | None, Query()] = None,
    min_transactions: int = Query(default=25, ge=1),
    min_price: float = Query(default=0, ge=0),
    max_price: float | None = Query(default=None, gt=0),
):
    return services.area_summary(years, parse_csv(property_types), parse_csv(areas), min_transactions, min_price, max_price)


@app.get("/prediction/options")
def get_prediction_options(
    area_name_en: str | None = None,
    property_sub_type_en: str | None = None,
    property_type_en: str | None = None,
    property_usage_en: str | None = None,
    rooms_en: str | None = None,
    reg_type_en: str | None = None,
    procedure_name_en: str | None = None,
    advertised_area: str | None = None,
):
    scopes = {
        "area_name_en": area_name_en,
        "property_sub_type_en": property_sub_type_en,
        "property_type_en": property_type_en,
        "property_usage_en": property_usage_en,
        "rooms_en": rooms_en,
        "reg_type_en": reg_type_en,
        "procedure_name_en": procedure_name_en,
        "advertised_area": advertised_area,
    }
    return services.prediction_options({key: value for key, value in scopes.items() if value})


@app.post("/predict/price")
def predict_price(payload: PricePredictionRequest):
    try:
        return services.predict_price(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/roi/calculate")
def calculate_roi(payload: RoiRequest):
    return services.roi(payload.model_dump())


@app.get("/opportunities")
def get_opportunities(
    years: Annotated[list[int] | None, Query()] = None,
    property_types: Annotated[list[str] | None, Query()] = None,
    areas: Annotated[list[str] | None, Query()] = None,
    min_transactions: int = Query(default=100, ge=1),
    min_price: float = Query(default=0, ge=0),
    max_price: float | None = Query(default=None, gt=0),
):
    return services.opportunities(years, parse_csv(property_types), parse_csv(areas), min_transactions, min_price, max_price)


@app.get("/model/performance")
def model_performance():
    return services.model_performance()
