from pydantic import BaseModel, Field


class CountryDTO(BaseModel):
    country_code: str
    country_name: str
    risk_factor: float
    is_unfriendly: bool = False
    sanctions_regime: str | None = None


class AnalogOptionDTO(BaseModel):
    analog_id: int
    name: str
    manufacturer: str
    country_code: str
    unit_cost_rub: float
    redesign_cost_rub: float
    lead_time_days: int
    compatibility_score: float
    compatibility_status: str = "FULL_COMPATIBLE"
    description: str = ""


class ComponentNodeDTO(BaseModel):
    id: int
    name: str
    article: str
    tier: int
    country_code: str
    manufacturer: str
    hs_code: str
    unit_cost_rub: float
    cost_rub: float
    quantity: float
    criticality: float
    country_risk: float
    analog_availability: float
    analog_status: str = "NO_ANALOGS"
    cfi_score: float
    is_chokepoint: bool
    parent_id: int | None = None
    children: list["ComponentNodeDTO"] = Field(default_factory=list)
    analogs: list[AnalogOptionDTO] = Field(default_factory=list)
    notes: str = ""


class ProductBOMResponseDTO(BaseModel):
    product_id: int
    product_name: str
    article: str
    category: str
    target_industry: str = ""
    enterprise_name: str = ""
    enterprise_inn: str = ""
    enterprise_city: str = ""
    is_strategic: bool = False
    strategic_priority: str = "NORMAL"
    total_cost_rub: float
    paper_localization_pct: float
    defacto_localization_pct: float
    vulnerability_gap_pct: float
    total_components_count: int
    chokepoints_count: int
    overall_cfi_max: float
    root_components: list[ComponentNodeDTO] = Field(default_factory=list)


class CreateProductDTO(BaseModel):
    name: str
    article: str
    category: str = "Лесозаготовительная техника"
    target_industry: str = "28.3 Лесозаготовительное машиностроение"
    enterprise_name: str = "АО «Лестехмаш»"
    enterprise_inn: str | None = "3525184920"
    enterprise_city: str | None = "г. Вологда"
    total_cost_rub: float = 0.0
    description: str | None = None
    audit_standard: str | None = "ПП РФ № 719"
    okpd2_code: str | None = None
    okpd2_name: str | None = None
    tnved_code: str | None = None
    normative_year: int | None = 2025
    rep_level: int | None = None
    eskd_decimal: str | None = None


class CreateComponentDTO(BaseModel):
    parent_id: int | None = None
    name: str
    article: str
    tier: int = Field(default=1, ge=1, le=3)
    hs_code: str = ""
    country_code: str = "RU"
    manufacturer: str = ""
    unit_cost_rub: float = 0.0
    quantity: float = 1.0
    criticality: float = 1.0
    analog_status: str = "NO_ANALOGS" # 'FULL_COMPATIBLE', 'REQUIRES_REWORK', 'POORLY_COMPATIBLE', 'NO_ANALOGS'
    # Опционально создание аналога сразу
    analog_name: str | None = None
    analog_manufacturer: str | None = None
    analog_country_code: str | None = None
    analog_cost_rub: float | None = None
    notes: str | None = None


class UpdateComponentDTO(BaseModel):
    name: str | None = None
    article: str | None = None
    unit_cost_rub: float | None = None
    quantity: float | None = None
    country_code: str | None = None
    manufacturer: str | None = None
    criticality: float | None = None
    analog_status: str | None = None
    notes: str | None = None


class CreateAnalogDTO(BaseModel):
    name: str
    manufacturer: str = ""
    country_code: str = "RU"
    unit_cost_rub: float = 0.0
    redesign_cost_rub: float = 0.0
    lead_time_days: int = 30
    compatibility_score: float = 1.0
    compatibility_status: str = "FULL_COMPATIBLE"
    description: str | None = None


class SubstituteAnalogRequestDTO(BaseModel):
    component_id: int
    analog_id: int


class SubstituteAnalogResponseDTO(BaseModel):
    success: bool
    component_id: int
    component_name: str
    substituted_with: str
    old_cfi: float
    new_cfi: float
    new_defacto_localization_pct: float
    cost_delta_rub: float
    redesign_investment_rub: float
    lead_time_days: int
    commentary: str
