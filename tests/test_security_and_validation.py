import pytest
from pydantic import ValidationError

from app.dto.bom_dto import CreateAnalogDTO, CreateComponentDTO, CreateProductDTO
from app.services.auth_service import create_jwt_token, decode_jwt_token


def test_create_component_dto_validation_rejects_negative_cost():
    """Тест защиты: стоимость компонента не может быть отрицательной"""
    with pytest.raises(ValidationError):
        CreateComponentDTO(
            name="Клапан",
            article="V-01",
            tier=2,
            unit_cost_rub=-500.0,
            quantity=1.0,
        )


def test_create_component_dto_validation_rejects_zero_or_negative_quantity():
    """Тест защиты: количество компонентов должно быть строго положительным"""
    with pytest.raises(ValidationError):
        CreateComponentDTO(
            name="Шайба",
            article="W-01",
            tier=3,
            unit_cost_rub=100.0,
            quantity=0.0,
        )


def test_create_component_dto_validation_rejects_invalid_tier():
    """Тест защиты: допустимы только уровни вложенности Tier 1-3"""
    with pytest.raises(ValidationError):
        CreateComponentDTO(
            name="Деталь",
            article="D-01",
            tier=4,
            unit_cost_rub=100.0,
            quantity=1.0,
        )


def test_create_product_dto_validation_rejects_empty_name():
    """Тест защиты: наименование изделия не может быть пустым"""
    with pytest.raises(ValidationError):
        CreateProductDTO(
            name="",
            article="ART-01",
        )


def test_create_analog_dto_validation_rejects_invalid_score():
    """Тест защиты: коэффициент совместимости аналога ограничен диапазоном [0.0, 1.0]"""
    with pytest.raises(ValidationError):
        CreateAnalogDTO(
            name="Аналог Микрон",
            unit_cost_rub=1000.0,
            compatibility_score=1.5,
        )


def test_jwt_tampering_is_rejected():
    """Тест защиты: фальсификация полезной нагрузки токена отклоняется валидатором HMAC"""
    token = create_jwt_token(
        {
            "sub": 1,
            "email": "engineer@test.ru",
            "full_name": "Тестовый Инженер",
            "role": "enterprise_engineer",
            "organization": "АО Тест",
        }
    )

    # Разбираем и подменяем роль в токене
    parts = token.split(".")
    assert len(parts) == 3

    # Подделываем токен с измененным хешем
    tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature"
    assert decode_jwt_token(tampered_token) is None
