import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.auth_router import UserResponse, require_enterprise_user
from app.database import get_db_session
from app.dto.bom_dto import (
    AnalogActionResponseDTO,
    ComponentActionResponseDTO,
    CountryDTO,
    CreateAnalogDTO,
    CreateComponentDTO,
    CreatedProductResponseDTO,
    CreateProductDTO,
    DeletedComponentResponseDTO,
    ProductBOMResponseDTO,
    ProductListItemDTO,
    SubstituteAnalogRequestDTO,
    SubstituteAnalogResponseDTO,
    UpdateComponentDTO,
)
from app.repositories.bom_repository import BOMRepository
from app.services.bom_service import (
    AnalogNotFoundError,
    BOMService,
    ComponentNotFoundError,
    ProductNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bom", tags=["Enterprise BOM & Manufacturing Hierarchy"])


async def get_bom_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BOMService:
    repo = BOMRepository(session)
    return BOMService(repo)


@router.get("/countries", response_model=list[CountryDTO])
async def list_countries(
    service: Annotated[BOMService, Depends(get_bom_service)],
) -> list[CountryDTO]:
    """Справочник юрисдикций и страновых коэффициентов риска Минпромторга РФ"""
    return await service.list_countries()


def verify_enterprise_access(user: UserResponse, enterprise_inn: str | None) -> None:
    """Проверка прав владения объектом (IDOR-защита): инспектор регулятора имеет полный доступ, инженер — только своего завода"""
    if user.role in ("regulator_admin", "admin"):
        return
    if user.inn and enterprise_inn and user.inn != enterprise_inn:
        logger.warning(
            "Попытка несанкционированного доступа (IDOR): пользователь %s (ИНН %s) пытается изменить объект завода с ИНН %s",
            user.email,
            user.inn,
            enterprise_inn,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещен: вы можете изменять спецификации только своего предприятия",
        )


@router.get("/products", response_model=list[ProductListItemDTO])
async def list_products(
    service: Annotated[BOMService, Depends(get_bom_service)],
) -> list[ProductListItemDTO]:
    """Список всех зарегистрированных изделий промышленных предприятий с расчетом метрик суверенитета"""
    return await service.list_products_with_metrics()


@router.post("/products", response_model=CreatedProductResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: CreateProductDTO,
    service: Annotated[BOMService, Depends(get_bom_service)],
    _user: Annotated[UserResponse, Depends(require_enterprise_user)],
) -> CreatedProductResponseDTO:
    """Регистрация нового изделия предприятием в системе Матрёшка.Аудит"""
    product = await service.create_product(payload)
    return CreatedProductResponseDTO(
        id=product.id,
        name=product.name,
        article=product.article,
        enterprise_name=product.enterprise_name,
        status="created",
    )


@router.get("/products/{product_id}/tree", response_model=ProductBOMResponseDTO)
async def get_product_bom_tree(
    product_id: int,
    service: Annotated[BOMService, Depends(get_bom_service)],
) -> ProductBOMResponseDTO:
    """Получить полное иерархическое дерево BOM (Tier 0-3) с расчётом O-Ring уязвимостей"""
    try:
        return await service.get_product_bom(product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.exception("Ошибка при получении дерева спецификации изделия #%s", product_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса при расчете дерева спецификации",
        ) from e


@router.post(
    "/products/{product_id}/components", response_model=ComponentActionResponseDTO, status_code=status.HTTP_201_CREATED
)
async def add_component(
    product_id: int,
    payload: CreateComponentDTO,
    service: Annotated[BOMService, Depends(get_bom_service)],
    _user: Annotated[UserResponse, Depends(require_enterprise_user)],
) -> ComponentActionResponseDTO:
    """Ручное добавление узла в спецификацию (Tier 1 ➔ Tier 2 ➔ Tier 3) с проверкой прав владения"""
    product = await service.repo.get_product(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Изделие #{product_id} не найдено")
    verify_enterprise_access(_user, product.enterprise_inn)

    try:
        comp = await service.add_component(product_id, payload)
        return ComponentActionResponseDTO(
            success=True,
            component_id=comp.id,
            name=comp.name,
            tier=comp.tier,
            cfi_score=comp.cfi_score,
            is_chokepoint=comp.is_chokepoint,
        )
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.exception("Ошибка при добавлении узла в спецификацию изделия #%s", product_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса при добавлении узла в спецификацию",
        ) from e


@router.put("/components/{component_id}", response_model=ComponentActionResponseDTO)
async def update_component(
    component_id: int,
    payload: UpdateComponentDTO,
    service: Annotated[BOMService, Depends(get_bom_service)],
    _user: Annotated[UserResponse, Depends(require_enterprise_user)],
) -> ComponentActionResponseDTO:
    """Редактирование параметров узла (цена, страна, аналог) с проверкой прав владения"""
    comp_obj = await service.repo.get_component(component_id)
    if not comp_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Компонент #{component_id} не найден")
    product = await service.repo.get_product(comp_obj.product_id)
    if product:
        verify_enterprise_access(_user, product.enterprise_inn)

    try:
        comp = await service.update_component(component_id, payload)
        return ComponentActionResponseDTO(
            success=True,
            component_id=comp.id,
            name=comp.name,
            tier=comp.tier,
            cfi_score=comp.cfi_score,
            is_chokepoint=comp.is_chokepoint,
        )
    except ComponentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.exception("Ошибка при обновлении компонента #%s", component_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса при обновлении компонента",
        ) from e


@router.delete("/components/{component_id}", response_model=DeletedComponentResponseDTO)
async def delete_component(
    component_id: int,
    service: Annotated[BOMService, Depends(get_bom_service)],
    _user: Annotated[UserResponse, Depends(require_enterprise_user)],
) -> DeletedComponentResponseDTO:
    """Удаление узла из дерева спецификации с проверкой прав владения"""
    comp_obj = await service.repo.get_component(component_id)
    if not comp_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Компонент #{component_id} не найден")
    product = await service.repo.get_product(comp_obj.product_id)
    if product:
        verify_enterprise_access(_user, product.enterprise_inn)

    try:
        await service.delete_component(component_id)
        return DeletedComponentResponseDTO(success=True, deleted_component_id=component_id)
    except ComponentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.exception("Ошибка при удалении компонента #%s", component_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса при удалении компонента",
        ) from e


@router.post(
    "/components/{component_id}/analogs", response_model=AnalogActionResponseDTO, status_code=status.HTTP_201_CREATED
)
async def add_component_analog(
    component_id: int,
    payload: CreateAnalogDTO,
    service: Annotated[BOMService, Depends(get_bom_service)],
    _user: Annotated[UserResponse, Depends(require_enterprise_user)],
) -> AnalogActionResponseDTO:
    """Прикрепление отечественного аналога к импортному узлу с проверкой прав владения"""
    comp_obj = await service.repo.get_component(component_id)
    if not comp_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Компонент #{component_id} не найден")
    product = await service.repo.get_product(comp_obj.product_id)
    if product:
        verify_enterprise_access(_user, product.enterprise_inn)

    try:
        analog = await service.add_analog(component_id, payload)
        return AnalogActionResponseDTO(
            success=True,
            analog_id=analog.id,
            name=analog.name,
            manufacturer=analog.manufacturer,
        )
    except ComponentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.exception("Ошибка при добавлении аналога к компоненту #%s", component_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса при добавлении аналога",
        ) from e


@router.post("/components/substitute-analog", response_model=SubstituteAnalogResponseDTO)
async def substitute_component_analog(
    payload: SubstituteAnalogRequestDTO,
    service: Annotated[BOMService, Depends(get_bom_service)],
    _user: Annotated[UserResponse, Depends(require_enterprise_user)],
) -> SubstituteAnalogResponseDTO:
    """Смоделировать замену импортного узла на отечественный аналог с проверкой прав владения"""
    comp_obj = await service.repo.get_component(payload.component_id)
    if not comp_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Компонент #{payload.component_id} не найден")
    product = await service.repo.get_product(comp_obj.product_id)
    if product:
        verify_enterprise_access(_user, product.enterprise_inn)

    try:
        return await service.substitute_analog(payload.component_id, payload.analog_id)
    except (ComponentNotFoundError, AnalogNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.exception("Ошибка при моделировании замещения аналога для узла #%s", payload.component_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса при пересчете замещения",
        ) from e
