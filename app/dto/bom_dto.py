from pydantic import BaseModel, Field


class AnalogOptionDTO(BaseModel):
    analog_id: int
    name: str
    manufacturer: str
    country_code: str
    unit_cost_rub: float
    redesign_cost_rub: float
    lead_time_days: int
    compatibility_score: float
    description: str = ""


class ComponentNodeDTO(BaseModel):
    id: int
    name: str
    article: str
    tier: int
    country_code: str
    manufacturer: str
    hs_code: str
    cost_rub: float
    quantity: float
    criticality: float
    country_risk: float
    analog_availability: float
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
    total_cost_rub: float
    paper_localization_pct: float
    defacto_localization_pct: float
    vulnerability_gap_pct: float
    total_components_count: int
    chokepoints_count: int
    overall_cfi_max: float
    root_components: list[ComponentNodeDTO] = Field(default_factory=list)


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
