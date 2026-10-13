import pytest
from app.services.bom_service import BOMService


def test_calculate_cfi_chokepoint():
    """Тест вычисления Critical Failure Index: STM32F407 (Швейцария/Франция)"""
    criticality = 1.0
    country_risk = 0.95
    analog_availability = 0.05
    cfi = BOMService.calculate_cfi(criticality, country_risk, analog_availability)
    assert cfi == 0.9025
    assert cfi >= 0.8  # Должен быть квалифицирован как chokepoint


def test_calculate_cfi_domestic_component():
    """Тест вычисления CFI для отечественного компонента"""
    criticality = 1.0
    country_risk = 0.0
    analog_availability = 1.0
    cfi = BOMService.calculate_cfi(criticality, country_risk, analog_availability)
    assert cfi == 0.0
    assert cfi < 0.8  # Не является узким горлышком


def test_calculate_cfi_after_substitution():
    """Тест снижения CFI после перехода на отечественный аналог MIK32 'Амур'"""
    criticality = 1.0
    new_country_risk = 0.05
    new_analog_availability = 0.75
    new_cfi = BOMService.calculate_cfi(criticality, new_country_risk, new_analog_availability)
    assert new_cfi == 0.0125
    assert new_cfi < 0.1  # Риск нейтрализован


def test_calculate_paper_localization_dynamic():
    """Тест вычисления бумажной локализации по Tier 1 адвалорной доле"""
    class MockComp:
        def __init__(self, tier, unit_cost_rub, quantity, country_code):
            self.tier = tier
            self.unit_cost_rub = unit_cost_rub
            self.quantity = quantity
            self.country_code = country_code

    comps = [
        MockComp(tier=1, unit_cost_rub=800000.0, quantity=1, country_code="RU"),
        MockComp(tier=1, unit_cost_rub=200000.0, quantity=1, country_code="DE"),
    ]
    paper_pct = BOMService.calculate_paper_localization(comps)
    assert paper_pct == 80.0


def test_calculate_defacto_localization_kremer_o_ring():
    """Тест непрерывной формулы Кремера O-Ring с мультипликативным штрафом узких горлышек"""
    class MockLeaf:
        def __init__(self, unit_cost_rub, quantity, country_code, country_risk, cfi_score, is_chokepoint, analog_status):
            self.unit_cost_rub = unit_cost_rub
            self.quantity = quantity
            self.country_code = country_code
            self.country_risk = country_risk
            self.cfi_score = cfi_score
            self.is_chokepoint = is_chokepoint
            self.analog_status = analog_status

    # Случай 1: 100% отечественный продукт без узких мест
    domestic_leaves = [
        MockLeaf(1000000.0, 1, "RU", 0.0, 0.0, False, "FULL_COMPATIBLE"),
    ]
    defacto_clean, max_cfi, choke_count = BOMService.calculate_defacto_localization(domestic_leaves, 1000000.0)
    assert defacto_clean == 100.0
    assert max_cfi == 0.0
    assert choke_count == 0

    # Случай 2: Скрытый импорт чипа (парадокс копеечного чипа)
    leaves_with_choke = [
        MockLeaf(990000.0, 1, "RU", 0.0, 0.0, False, "FULL_COMPATIBLE"),
        MockLeaf(10000.0, 1, "CH", 0.95, 0.9025, True, "NO_ANALOGS"),
    ]
    defacto_choked, max_cfi, choke_count = BOMService.calculate_defacto_localization(leaves_with_choke, 1000000.0)
    assert choke_count == 1
    assert max_cfi == 0.9025
    # Наличие O-Ring chokepoint с CFI=0.9025 дает штраф, де-факто существенно ниже 80%
    assert defacto_choked < 80.0
    assert defacto_choked > 0.0

