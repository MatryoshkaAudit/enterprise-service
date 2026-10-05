from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_manager
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
)

router = APIRouter(prefix="/api/v1/bom", tags=["Enterprise BOM"])


async def get_bom_service(
    session: AsyncSession = Depends(db_manager.get_session),
) -> BOMService:
    repo = BOMRepository(session)
    return BOMService(repo)


@router.get("/products", response_model=list[dict])
async def list_products(
    service: BOMService = Depends(get_bom_service),
):
    """Список зарегистрированных машиностроительных изделий"""
    products = await service.repo.get_all_products()
    return [
        {
            "id": p.id,
            "name": p.name,
            "article": p.article,
            "category": p.category,
            "total_cost_rub": p.total_cost_rub,
        }
        for p in products
    ]


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
