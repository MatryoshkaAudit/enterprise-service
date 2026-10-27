import pytest
from fastapi import HTTPException

from app.api.routers.auth_router import UserResponse
from app.api.routers.bom_router import verify_enterprise_access


def test_verify_enterprise_access_allows_same_inn():
    """Тест: инженер имеет доступ к изделиям своего предприятия (совпадение ИНН)"""
    user = UserResponse(
        id=1,
        email="engineer@lestechmash.ru",
        full_name="Смирнов Алексей Петрович",
        role="enterprise_engineer",
        organization="АО «Лестехмаш»",
        inn="3525184920",
    )
    # Не должно выбрасывать исключение
    verify_enterprise_access(user, "3525184920")


def test_verify_enterprise_access_rejects_foreign_inn_idor():
    """Тест IDOR-защиты: инженеру запрещено изменять изделия чужого предприятия"""
    user = UserResponse(
        id=1,
        email="engineer@lestechmash.ru",
        full_name="Смирнов Алексей Петрович",
        role="enterprise_engineer",
        organization="АО «Лестехмаш»",
        inn="3525184920",
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_enterprise_access(user, "3702654120")  # ИНН АО «Станкомаш-Холдинг»

    assert exc_info.value.status_code == 403
    assert "своего предприятия" in exc_info.value.detail


def test_verify_enterprise_access_allows_regulator_admin_any_inn():
    """Тест: инспектор регулятора Минпромторга имеет право межотраслевого надзора"""
    regulator = UserResponse(
        id=2,
        email="inspector@minpromtorg.gov.ru",
        full_name="Лесных Иван Сергеевич",
        role="regulator_admin",
        organization="Минпромторг РФ",
        inn="7705596339",
    )
    # Должен иметь доступ к любому предприятию
    verify_enterprise_access(regulator, "3525184920")
    verify_enterprise_access(regulator, "3702654120")
