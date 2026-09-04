from __future__ import annotations

from pydantic import BaseModel, Field


class PricePredictionRequest(BaseModel):
    procedure_name_en: str
    property_type_en: str
    property_sub_type_en: str
    property_usage_en: str
    reg_type_en: str
    area_name_en: str
    rooms_en: str
    has_parking: bool = True
    procedure_area: float = Field(gt=0)
    advertised_area: str | None = None
    year: int = Field(ge=2000, le=2035)
    month: int = Field(ge=1, le=12)


class RoiRequest(BaseModel):
    purchase_price: float = Field(gt=0)
    monthly_rent: float = Field(ge=0)
    annual_costs: float = Field(ge=0, default=0)
    closing_cost_rate: float = Field(ge=0, le=0.2, default=0.04)
    vacancy_rate: float = Field(ge=0, le=0.5, default=0.05)
    appreciation_rate: float = Field(ge=-0.5, le=0.5, default=0.03)
