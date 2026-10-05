import logging
from app.repositories.bom_repository import BOMRepository
from app.dto.bom_dto import (
    ProductBOMResponseDTO,
    ComponentNodeDTO,
    AnalogOptionDTO,
    SubstituteAnalogResponseDTO,
)
from matryoshka_db.db_models import Component

logger = logging.getLogger(__name__)


class BOMServiceError(Exception):
    """Базовое исключение сервиса BOM"""


class ProductNotFoundError(BOMServiceError):
    """Изделие не найдено"""


class ComponentNotFoundError(BOMServiceError):
    """Компонент не найден"""


class AnalogNotFoundError(BOMServiceError):
    """Аналог не найден"""


class BOMService:
    def __init__(self, repo: BOMRepository):
        self.repo = repo

    @staticmethod
    def calculate_cfi(criticality: float, country_risk: float, analog_availability: float) -> float:
        """Расчёт индекса критического отказа CFI = Criticality * Risk * (1 - AnalogAvail)"""
        return round(criticality * country_risk * (1.0 - analog_availability), 4)

    def _build_tree(self, components: list[Component]) -> list[ComponentNodeDTO]:
        """Превращение плоского списка комплектующих в многоуровневое иерархическое дерево (Tier 1-3)"""
        node_map: dict[int, ComponentNodeDTO] = {}
        roots: list[ComponentNodeDTO] = []

        for comp in components:
            dto = ComponentNodeDTO(
                id=comp.id,
                name=comp.name,
                article=comp.article,
                tier=comp.tier,
                country_code=comp.country_code,
                manufacturer=comp.manufacturer,
                hs_code=comp.hs_code or "",
                cost_rub=comp.unit_cost_rub * comp.quantity,
                quantity=comp.quantity,
                criticality=comp.criticality,
                country_risk=comp.country_risk,
                analog_availability=comp.analog_availability,
                cfi_score=comp.cfi_score,
                is_chokepoint=comp.is_chokepoint,
                parent_id=comp.parent_id,
                analogs=[
                    AnalogOptionDTO(
                        analog_id=a.id,
                        name=a.name,
                        manufacturer=a.manufacturer,
                        country_code=a.country_code,
                        unit_cost_rub=a.unit_cost_rub,
                        redesign_cost_rub=a.redesign_cost_rub,
                        lead_time_days=a.lead_time_days,
                        compatibility_score=a.compatibility_score,
                        description=a.description or "",
                    )
                    for a in comp.analogs
                ],
                notes=comp.notes or "",
            )
            node_map[comp.id] = dto

        for comp in components:
            dto = node_map[comp.id]
            if comp.parent_id and comp.parent_id in node_map:
                node_map[comp.parent_id].children.append(dto)
            else:
                roots.append(dto)

        return roots

    async def get_product_bom(self, product_id: int) -> ProductBOMResponseDTO:
        product = await self.repo.get_product(product_id)
        if not product:
            raise ProductNotFoundError(f"Изделие с ID {product_id} не найдено")

        components = await self.repo.get_product_components(product_id)
        if not components:
            return ProductBOMResponseDTO(
                product_id=product.id,
                product_name=product.name,
                article=product.article,
                category=product.category,
                total_cost_rub=product.total_cost_rub,
                paper_localization_pct=0.0,
                defacto_localization_pct=0.0,
                vulnerability_gap_pct=0.0,
                total_components_count=0,
                chokepoints_count=0,
                overall_cfi_max=0.0,
                root_components=[],
            )

        # 1. Расчёт формальной ("бумажной") локализации по первому уровню
        tier_1_items = [c for c in components if c.tier == 1]
        tier_1_total = sum(c.unit_cost_rub * c.quantity for c in tier_1_items) or product.total_cost_rub
        tier_1_domestic = sum(
            c.unit_cost_rub * c.quantity for c in tier_1_items if c.country_code in ("RU", "BY")
        )
        paper_loc_pct = round((tier_1_domestic / tier_1_total) * 100.0, 1) if tier_1_total > 0 else 0.0

        # 2. Расчёт реальной ("де-факто") локализации по листовым узлам графа с учётом страновых рисков
        # Листовые узлы — это компоненты, у которых нет дочерних элементов (глубинные комплектующие)
        parent_ids = {c.parent_id for c in components if c.parent_id is not None}
        leaf_components = [c for c in components if c.id not in parent_ids]
        
        leaf_total_cost = sum(c.unit_cost_rub * c.quantity for c in leaf_components)
        if leaf_total_cost == 0:
            leaf_total_cost = tier_1_total

        # Де-факто доля с весом риска юрисдикции
        defacto_weighted_sum = sum(
            (c.unit_cost_rub * c.quantity) * (1.0 - c.country_risk) for c in leaf_components
        )
        defacto_loc_pct = round((defacto_weighted_sum / leaf_total_cost) * 100.0, 1)

        # 3. Анализ O-Ring уязвимостей
        chokepoint_items = [c for c in components if c.is_chokepoint or c.cfi_score >= 0.8]
        chokepoints_count = len(chokepoint_items)
        overall_cfi_max = max((c.cfi_score for c in components), default=0.0)

        # Построение иерархического дерева
        tree = self._build_tree(components)

        return ProductBOMResponseDTO(
            product_id=product.id,
            product_name=product.name,
            article=product.article,
            category=product.category,
            total_cost_rub=product.total_cost_rub,
            paper_localization_pct=paper_loc_pct,
            defacto_localization_pct=defacto_loc_pct,
            vulnerability_gap_pct=round(paper_loc_pct - defacto_loc_pct, 1),
            total_components_count=len(components),
            chokepoints_count=chokepoints_count,
            overall_cfi_max=overall_cfi_max,
            root_components=tree,
        )

    async def substitute_analog(self, component_id: int, analog_id: int) -> SubstituteAnalogResponseDTO:
        comp = await self.repo.get_component(component_id)
        if not comp:
            raise ComponentNotFoundError(f"Компонент с ID {component_id} не найден")

        analog = await self.repo.get_analog(analog_id)
        if not analog or analog.component_id != component_id:
            raise AnalogNotFoundError(f"Аналог с ID {analog_id} не найден для данного узла")

        old_cfi = comp.cfi_score
        
        # Обновление атрибутов компонента отечественным аналогом
        comp.name = f"{analog.name} (Замещение)"
        comp.country_code = analog.country_code
        comp.manufacturer = analog.manufacturer
        comp.country_risk = 0.05 if analog.country_code in ("RU", "BY") else 0.3
        comp.analog_availability = analog.compatibility_score
        comp.unit_cost_rub = analog.unit_cost_rub
        comp.lead_time_days = analog.lead_time_days

        new_cfi = self.calculate_cfi(comp.criticality, comp.country_risk, comp.analog_availability)
        comp.cfi_score = new_cfi
        comp.is_chokepoint = new_cfi >= 0.8

        await self.repo.update_component(comp)

        # Пересчёт сводной локализации изделия
        bom_summary = await self.get_product_bom(comp.product_id)

        commentary = (
            f"Успешное замещение импортного узла на отечественный {analog.name}. "
            f"Индекс уязвимости CFI снизился с {old_cfi:.2f} до {new_cfi:.2f}. "
            f"Требуемые инвестиции в редизайн схемотехники: {analog.redesign_cost_rub:,.0f} ₽. "
            f"Срок внедрения в производство: {analog.lead_time_days} дней."
        )

        return SubstituteAnalogResponseDTO(
            success=True,
            component_id=comp.id,
            component_name=comp.name,
            substituted_with=analog.name,
            old_cfi=old_cfi,
            new_cfi=new_cfi,
            new_defacto_localization_pct=bom_summary.defacto_localization_pct,
            cost_delta_rub=analog.unit_cost_rub - comp.unit_cost_rub,
            redesign_investment_rub=analog.redesign_cost_rub,
            lead_time_days=analog.lead_time_days,
            commentary=commentary,
        )
