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
