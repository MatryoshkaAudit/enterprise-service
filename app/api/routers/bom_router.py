from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.repositories.bom_repository import BOMRepository
from app.services.bom_service import (
    BOMService,
    ProductNotFoundError,
    ComponentNotFoundError,
    AnalogNotFoundError,
)
from app.dto.bom_dto import (
    ProductBOMResponseDTO,
    SubstituteAnalogRequestDTO,
    SubstituteAnalogResponseDTO,
    CountryDTO,
    CreateProductDTO,
    CreateComponentDTO,
    UpdateComponentDTO,
    CreateAnalogDTO,
    ComponentNodeDTO,
    AnalogOptionDTO,
)

router = APIRouter(prefix="/api/v1/bom", tags=["Enterprise BOM & Manufacturing Hierarchy"])


async def get_bom_service(
    session: AsyncSession = Depends(get_db_session),
) -> BOMService:
    repo = BOMRepository(session)
    return BOMService(repo)


@router.get("/countries", response_model=list[CountryDTO])
async def list_countries(
    service: BOMService = Depends(get_bom_service),
):
    """Справочник юрисдикций и страновых коэффициентов риска Минпромторга РФ"""
    return await service.list_countries()


@router.get("/products", response_model=list[dict])
async def list_products(
    service: BOMService = Depends(get_bom_service),
):
    """Список всех зарегистрированных изделий промышленных предприятий"""
    products = await service.repo.get_all_products()
    return [
        {
            "id": p.id,
            "name": p.name,
            "article": p.article,
            "category": p.category,
            "target_industry": p.target_industry,
            "enterprise_name": p.enterprise_name,
            "enterprise_inn": p.enterprise_inn,
            "enterprise_city": p.enterprise_city,
            "total_cost_rub": p.total_cost_rub,
            "is_strategic": p.is_strategic,
            "strategic_priority": p.strategic_priority,
            "strategic_notes": p.strategic_notes,
            "description": p.description,
        }
        for p in products
    ]


@router.post("/products", response_model=dict)
async def create_product(
    payload: CreateProductDTO,
    service: BOMService = Depends(get_bom_service),
):
    """Регистрация нового изделия предприятием в системе Матрёшка.Аудит"""
    product = await service.create_product(payload)
    return {
        "id": product.id,
        "name": product.name,
        "article": product.article,
        "enterprise_name": product.enterprise_name,
        "status": "created",
    }


@router.get("/products/{product_id}/tree", response_model=ProductBOMResponseDTO)
async def get_product_bom_tree(
    product_id: int,
    service: BOMService = Depends(get_bom_service),
):
    """Получить полное иерархическое дерево BOM (Tier 0-3) с расчётом O-Ring уязвимостей"""
    try:
        return await service.get_product_bom(product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервиса: {str(e)}")


@router.post("/products/{product_id}/components", response_model=dict)
async def add_component(
    product_id: int,
    payload: CreateComponentDTO,
    service: BOMService = Depends(get_bom_service),
):
    """Ручное добавление узла в спецификацию (Tier 1 ➔ Tier 2 ➔ Tier 3)"""
    try:
        comp = await service.add_component(product_id, payload)
        return {
            "success": True,
            "component_id": comp.id,
            "name": comp.name,
            "tier": comp.tier,
            "cfi_score": comp.cfi_score,
            "is_chokepoint": comp.is_chokepoint,
        }
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка добавления узла: {str(e)}")


@router.put("/components/{component_id}", response_model=dict)
async def update_component(
    component_id: int,
    payload: UpdateComponentDTO,
    service: BOMService = Depends(get_bom_service),
):
    """Редактирование параметров узла (цена, страна, аналог)"""
    try:
        comp = await service.update_component(component_id, payload)
        return {
            "success": True,
            "component_id": comp.id,
            "name": comp.name,
            "cfi_score": comp.cfi_score,
            "is_chokepoint": comp.is_chokepoint,
        }
    except ComponentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обновления узла: {str(e)}")


@router.delete("/components/{component_id}", response_model=dict)
async def delete_component(
    component_id: int,
    service: BOMService = Depends(get_bom_service),
):
    """Удаление узла из дерева спецификации"""
    try:
        await service.delete_component(component_id)
        return {"success": True, "deleted_component_id": component_id}
    except ComponentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {str(e)}")


@router.post("/components/{component_id}/analogs", response_model=dict)
async def add_component_analog(
    component_id: int,
    payload: CreateAnalogDTO,
    service: BOMService = Depends(get_bom_service),
):
    """Прикрепление отечественного аналога к импортному узлу"""
    try:
        analog = await service.add_analog(component_id, payload)
        return {
            "success": True,
            "analog_id": analog.id,
            "name": analog.name,
            "manufacturer": analog.manufacturer,
        }
    except ComponentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка добавления аналога: {str(e)}")


@router.post("/components/substitute-analog", response_model=SubstituteAnalogResponseDTO)
async def substitute_component_analog(
    payload: SubstituteAnalogRequestDTO,
    service: BOMService = Depends(get_bom_service),
):
    """Смоделировать замену импортного узла на отечественный аналог из каталога"""
    try:
        return await service.substitute_analog(payload.component_id, payload.analog_id)
    except (ComponentNotFoundError, AnalogNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка пересчёта замещения: {str(e)}")
