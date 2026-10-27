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
    lead_time_days: int = 14
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
    name: str = Field(min_length=1, max_length=255)
    article: str = Field(min_length=1, max_length=100)
    category: str = Field(default="Лесозаготовительная техника", max_length=100)
    target_industry: str = Field(default="28.3 Лесозаготовительное машиностроение", max_length=100)
    enterprise_name: str = Field(default="АО «Лестехмаш»", max_length=255)
    enterprise_inn: str | None = Field(default="3525184920", max_length=20)
    enterprise_city: str | None = Field(default="г. Вологда", max_length=100)
    total_cost_rub: float = Field(default=0.0, ge=0.0)
    description: str | None = Field(default=None, max_length=1000)
    audit_standard: str | None = "ПП РФ № 719"
    okpd2_code: str | None = None
    okpd2_name: str | None = None
    tnved_code: str | None = None
    normative_year: int | None = 2025
    rep_level: int | None = None
    eskd_decimal: str | None = None


class CreateComponentDTO(BaseModel):
    parent_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    article: str = Field(min_length=1, max_length=100)
    tier: int = Field(default=1, ge=1, le=3)
    hs_code: str = Field(default="", max_length=20)
    country_code: str = Field(default="RU", min_length=2, max_length=3)
    manufacturer: str = Field(default="", max_length=255)
    unit_cost_rub: float = Field(default=0.0, ge=0.0)
    quantity: float = Field(default=1.0, gt=0.0)
    criticality: float = Field(default=1.0, ge=0.0, le=1.0)
    lead_time_days: int = Field(default=14, ge=0)
    analog_status: str = "NO_ANALOGS"  # 'FULL_COMPATIBLE', 'REQUIRES_REWORK', 'POORLY_COMPATIBLE', 'NO_ANALOGS'
    # Опционально создание аналога сразу
    analog_name: str | None = Field(default=None, max_length=255)
    analog_manufacturer: str | None = Field(default=None, max_length=255)
    analog_country_code: str | None = Field(default=None, min_length=2, max_length=3)
    analog_cost_rub: float | None = Field(default=None, ge=0.0)
    analog_lead_time_days: int | None = Field(default=None, ge=0)
    analog_redesign_cost_rub: float | None = Field(default=None, ge=0.0)
    notes: str | None = Field(default=None, max_length=500)


class UpdateComponentDTO(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    article: str | None = Field(default=None, max_length=100)
    hs_code: str | None = Field(default=None, max_length=20)
    unit_cost_rub: float | None = Field(default=None, ge=0.0)
    quantity: float | None = Field(default=None, gt=0.0)
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    manufacturer: str | None = Field(default=None, max_length=255)
    criticality: float | None = Field(default=None, ge=0.0, le=1.0)
    analog_status: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    redesign_cost_rub: float | None = Field(default=None, ge=0.0)
    analog_name: str | None = Field(default=None, max_length=255)
    analog_manufacturer: str | None = Field(default=None, max_length=255)
    analog_cost_rub: float | None = Field(default=None, ge=0.0)
    commercial_offer_doc: str | None = None
    notes: str | None = Field(default=None, max_length=500)


class CreateAnalogDTO(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    manufacturer: str = Field(default="", max_length=255)
    country_code: str = Field(default="RU", min_length=2, max_length=3)
    unit_cost_rub: float = Field(default=0.0, ge=0.0)
    redesign_cost_rub: float = Field(default=0.0, ge=0.0)
    lead_time_days: int = Field(default=30, ge=0)
    compatibility_score: float = Field(default=1.0, ge=0.0, le=1.0)
    compatibility_status: str = "FULL_COMPATIBLE"
    description: str | None = Field(default=None, max_length=500)


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


class ProductListItemDTO(BaseModel):
    id: int
    name: str
    article: str
    category: str
    target_industry: str
    enterprise_name: str
    enterprise_inn: str | None = None
    enterprise_city: str | None = None
    total_cost_rub: float
    is_strategic: bool = False
    strategic_priority: str = "NORMAL"
    strategic_notes: str | None = None
    description: str | None = None
    paper_localization_pct: float = 100.0
    defacto_localization_pct: float = 100.0
    vulnerability_gap_pct: float = 0.0
    chokepoints_count: int = 0
    achieved_points: int = 78
    required_points: int = 70


class CreatedProductResponseDTO(BaseModel):
    id: int
    name: str
    article: str
    enterprise_name: str
    status: str = "created"


class ComponentActionResponseDTO(BaseModel):
    success: bool
    component_id: int
    name: str
    tier: int | None = None
    cfi_score: float
    is_chokepoint: bool


class DeletedComponentResponseDTO(BaseModel):
    success: bool
    deleted_component_id: int


class AnalogActionResponseDTO(BaseModel):
    success: bool
    analog_id: int
    name: str
    manufacturer: str
