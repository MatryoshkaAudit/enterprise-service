import logging

from app.dto.bom_dto import (
    AnalogOptionDTO,
    ComponentNodeDTO,
    CountryDTO,
    CreateAnalogDTO,
    CreateComponentDTO,
    CreateProductDTO,
    ProductBOMResponseDTO,
    ProductListItemDTO,
    SubstituteAnalogResponseDTO,
    UpdateComponentDTO,
)
from app.repositories.bom_repository import BOMRepository
from matryoshka_db.db_models import Analog, Component, Product

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
    def get_analog_avail_score(status: str) -> float:
        """Перевод текстового статуса наличия аналогов в коэффициент [0.0 .. 1.0]"""
        status_map = {
            "FULL_COMPATIBLE": 1.0,  # Совместим полностью (Прямой pin-to-pin)
            "REQUIRES_REWORK": 0.7,  # Требует доработки (Схемотехника/ПО)
            "POORLY_COMPATIBLE": 0.2,  # Практически несовместим
            "NO_ANALOGS": 0.0,  # Аналоги отсутствуют
        }
        return status_map.get(status.upper(), 0.0)

    @staticmethod
    def calculate_cfi(criticality: float, country_risk: float, analog_availability: float) -> float:
        """
        Расчёт индекса критического узкого горлышка:
        CFI = Criticality * Risk * (1 - AnalogAvail)
        """
        return round(float(criticality) * float(country_risk) * (1.0 - float(analog_availability)), 4)

    @staticmethod
    def calculate_paper_localization(components: list) -> float:
        """
        Де-юре (бумажная) локализация по нормам ПП РФ № 719 / СТ-1.
        Рассчитывается динамически как стоимостная доля агрегатов высшего порядка (Tier-1),
        происходящих из контура ЕАЭС (RU, BY, KZ, AM, KG).
        """
        if not components:
            return 100.0

        tier1 = [c for c in components if getattr(c, "tier", None) == 1]
        if tier1:
            tot_cost = sum(c.unit_cost_rub * c.quantity for c in tier1)
            if tot_cost > 0:
                eaeu_cost = sum(
                    c.unit_cost_rub * c.quantity
                    for c in tier1
                    if getattr(c, "country_code", "") in ("RU", "BY", "KZ", "AM", "KG")
                )
                return round((eaeu_cost / tot_cost) * 100.0, 1)
            return 100.0

        top_level = [c for c in components if getattr(c, "parent_id", None) is None]
        if top_level:
            tot_cost = sum(c.unit_cost_rub * c.quantity for c in top_level)
            if tot_cost > 0:
                eaeu_cost = sum(
                    c.unit_cost_rub * c.quantity
                    for c in top_level
                    if getattr(c, "country_code", "") in ("RU", "BY", "KZ", "AM", "KG")
                )
                return round((eaeu_cost / tot_cost) * 100.0, 1)
        return 100.0

    @staticmethod
    def calculate_defacto_localization(leaf_components: list, total_leaf_cost: float) -> tuple[float, float, int]:
        """
        Непрерывный расчет де-факто суверенитета по теории O-Ring Майкла Кремера:
        1. Взвешенный суверенитет листьев дерева: Loc_raw = sum( (Cost_i / Total) * (1 - Risk_i) * omega_i )
        2. Мультипликатор надежности Кремера: Omega = prod(1 - 0.25 * CFI_j) для всех chokepoint-узлов (CFI >= 0.70).
        Возвращает: (defacto_loc_pct, overall_cfi_max, chokepoints_count).
        """
        if not leaf_components or total_leaf_cost <= 0:
            return (100.0, 0.0, 0)

        weighted_safe_sum = 0.0
        for c in leaf_components:
            cost = c.unit_cost_rub * c.quantity
            status = getattr(c, "analog_status", "") or "NO_ANALOGS"
            country = getattr(c, "country_code", "")
            analog_w = (
                1.0
                if status == "FULL_COMPATIBLE"
                else (
                    0.7
                    if status == "REQUIRES_REWORK"
                    else (0.2 if status == "POORLY_COMPATIBLE" else (1.0 if country in ("RU", "BY") else 0.0))
                )
            )
            safe_factor = (1.0 - float(getattr(c, "country_risk", 0.0))) * analog_w
            weighted_safe_sum += (cost / total_leaf_cost) * safe_factor

        raw_defacto_pct = round(weighted_safe_sum * 100.0, 1)

        chokepoints = [
            c for c in leaf_components if getattr(c, "is_chokepoint", False) or getattr(c, "cfi_score", 0.0) >= 0.70
        ]
        chokepoints_count = len(chokepoints)
        overall_cfi_max = max((getattr(c, "cfi_score", 0.0) for c in leaf_components), default=0.0)

        o_ring_multiplier = 1.0
        for choke in chokepoints:
            cfi = getattr(choke, "cfi_score", 0.8)
            o_ring_multiplier *= 1.0 - 0.25 * float(cfi)

        defacto_loc_pct = round(raw_defacto_pct * o_ring_multiplier, 1)
        return (defacto_loc_pct, overall_cfi_max, chokepoints_count)

    async def list_countries(self) -> list[CountryDTO]:
        """Получение полного государственного справочника стран с весами рисков"""
        countries = await self.repo.get_all_countries()
        return [
            CountryDTO(
                country_code=c.country_code,
                country_name=c.country_name,
                risk_factor=c.risk_factor,
                is_unfriendly=c.is_unfriendly,
                sanctions_regime=c.sanctions_regime,
            )
            for c in countries
        ]

    async def list_products_with_metrics(self) -> list[ProductListItemDTO]:
        """Возвращает список изделий с динамически рассчитанными метриками O-Ring суверенитета"""
        products = await self.repo.get_all_products()
        results: list[ProductListItemDTO] = []
        for p in products:
            bom = await self.get_product_bom(p.id)
            cert = await self.repo.get_product_certificate(p.id)
            rule = await self.repo.get_policy_rule(p.target_industry)
            achieved = (
                cert.pp719_points
                if cert and cert.pp719_points > 0
                else (rule.min_points_required if rule and bom.defacto_localization_pct >= 50 else 0)
            )
            required = rule.min_points_required if rule else 0
            results.append(
                ProductListItemDTO(
                    id=p.id,
                    name=p.name,
                    article=p.article,
                    category=p.category,
                    target_industry=p.target_industry,
                    enterprise_name=p.enterprise_name,
                    enterprise_inn=p.enterprise_inn,
                    enterprise_city=p.enterprise_city,
                    total_cost_rub=p.total_cost_rub,
                    is_strategic=p.is_strategic,
                    strategic_priority=p.strategic_priority,
                    strategic_notes=p.strategic_notes,
                    description=p.description,
                    paper_localization_pct=bom.paper_localization_pct,
                    defacto_localization_pct=bom.defacto_localization_pct,
                    vulnerability_gap_pct=bom.vulnerability_gap_pct,
                    chokepoints_count=bom.chokepoints_count,
                    achieved_points=achieved,
                    required_points=required,
                )
            )
        return results

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
                unit_cost_rub=comp.unit_cost_rub,
                cost_rub=round(comp.unit_cost_rub * comp.quantity, 2),
                quantity=comp.quantity,
                criticality=comp.criticality,
                country_risk=comp.country_risk,
                analog_availability=comp.analog_availability,
                analog_status=comp.analog_status or "NO_ANALOGS",
                lead_time_days=comp.lead_time_days or 14,
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
                        compatibility_status=getattr(a, "compatibility_status", "FULL_COMPATIBLE") or "FULL_COMPATIBLE",
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
        """Полная декомпозиция изделия с расчетом научной формулы де-факто локализации и CFI"""
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
                target_industry=product.target_industry,
                enterprise_name=product.enterprise_name,
                enterprise_inn=product.enterprise_inn or "",
                enterprise_city=product.enterprise_city or "",
                is_strategic=product.is_strategic,
                strategic_priority=product.strategic_priority,
                total_cost_rub=product.total_cost_rub,
                paper_localization_pct=100.0,
                defacto_localization_pct=100.0,
                vulnerability_gap_pct=0.0,
                total_components_count=0,
                chokepoints_count=0,
                overall_cfi_max=0.0,
                root_components=[],
            )

        # Синхронизация страновых рисков из справочника
        countries = {c.country_code: c.risk_factor for c in await self.repo.get_all_countries()}
        for comp in components:
            if comp.country_code in countries:
                comp.country_risk = countries[comp.country_code]
            comp.cfi_score = self.calculate_cfi(comp.criticality, comp.country_risk, comp.analog_availability)
            comp.is_chokepoint = comp.cfi_score >= 0.70

        # Поиск листьев дерева (компоненты без дочерних узлов)
        parent_ids = {c.parent_id for c in components if c.parent_id is not None}
        leaf_components = [c for c in components if c.id not in parent_ids]

        total_leaf_cost = sum(c.unit_cost_rub * c.quantity for c in leaf_components)
        if total_leaf_cost <= 0:
            total_leaf_cost = product.total_cost_rub or 1.0

        # Динамический расчет де-юре (бумажной) локализации по ПП РФ № 719 / СТ-1
        paper_loc_pct = self.calculate_paper_localization(components)

        # Динамический расчет де-факто технологического суверенитета по Кремеру (O-Ring)
        defacto_loc_pct, overall_cfi_max, chokepoints_count = self.calculate_defacto_localization(
            leaf_components, total_leaf_cost
        )

        vulnerability_gap_pct = max(0.0, round(paper_loc_pct - defacto_loc_pct, 1))

        tree = self._build_tree(components)

        return ProductBOMResponseDTO(
            product_id=product.id,
            product_name=product.name,
            article=product.article,
            category=product.category,
            target_industry=product.target_industry,
            enterprise_name=product.enterprise_name,
            enterprise_inn=product.enterprise_inn or "",
            enterprise_city=product.enterprise_city or "",
            is_strategic=product.is_strategic,
            strategic_priority=product.strategic_priority,
            total_cost_rub=product.total_cost_rub,
            paper_localization_pct=paper_loc_pct,
            defacto_localization_pct=defacto_loc_pct,
            vulnerability_gap_pct=vulnerability_gap_pct,
            total_components_count=len(components),
            chokepoints_count=chokepoints_count,
            overall_cfi_max=overall_cfi_max,
            root_components=tree,
        )

    async def create_product(self, dto: CreateProductDTO) -> Product:
        """Создание нового изделия предприятием"""
        product = Product(
            name=dto.name,
            article=dto.article,
            category=dto.category,
            target_industry=dto.target_industry,
            enterprise_name=dto.enterprise_name,
            enterprise_inn=dto.enterprise_inn,
            enterprise_city=dto.enterprise_city,
            total_cost_rub=dto.total_cost_rub,
            description=dto.description,
            is_strategic=False,
            strategic_priority="NORMAL",
        )
        return await self.repo.create_product(product)

    async def add_component(self, product_id: int, dto: CreateComponentDTO) -> Component:
        """Добавление компонента в спецификацию (Уровень 1, 2 или 3)"""
        product = await self.repo.get_product(product_id)
        if not product:
            raise ProductNotFoundError(f"Изделие с ID {product_id} не найдено")

        country = await self.repo.get_country(dto.country_code)
        country_risk = country.risk_factor if country else 0.5
        analog_avail = self.get_analog_avail_score(dto.analog_status)
        cfi = self.calculate_cfi(dto.criticality, country_risk, analog_avail)
        is_choke = cfi >= 0.70

        comp = Component(
            product_id=product_id,
            parent_id=dto.parent_id,
            name=dto.name,
            article=dto.article,
            tier=dto.tier,
            hs_code=dto.hs_code,
            country_code=dto.country_code.upper(),
            manufacturer=dto.manufacturer,
            unit_cost_rub=dto.unit_cost_rub,
            quantity=dto.quantity,
            criticality=dto.criticality,
            country_risk=country_risk,
            analog_status=dto.analog_status.upper(),
            analog_availability=analog_avail,
            cfi_score=cfi,
            is_chokepoint=is_choke,
            lead_time_days=dto.lead_time_days or 14,
            notes=dto.notes,
        )
        created_comp = await self.repo.create_component(comp)

        # Если сразу передан аналог
        if dto.analog_name:
            analog = Analog(
                component_id=created_comp.id,
                name=dto.analog_name,
                manufacturer=dto.analog_manufacturer or "",
                country_code=(dto.analog_country_code or "RU").upper(),
                unit_cost_rub=dto.analog_cost_rub or dto.unit_cost_rub,
                redesign_cost_rub=dto.analog_redesign_cost_rub or 0.0,
                compatibility_score=analog_avail if analog_avail > 0 else 0.8,
                compatibility_status=dto.analog_status.upper(),
                lead_time_days=dto.analog_lead_time_days or 30,
            )
            await self.repo.create_analog(analog)

        return created_comp

    async def update_component(self, component_id: int, dto: UpdateComponentDTO) -> Component:
        """Редактирование параметров узла"""
        comp = await self.repo.get_component(component_id)
        if not comp:
            raise ComponentNotFoundError(f"Компонент с ID {component_id} не найден")

        if dto.name is not None:
            comp.name = dto.name
        if dto.article is not None:
            comp.article = dto.article
        if dto.unit_cost_rub is not None:
            comp.unit_cost_rub = dto.unit_cost_rub
        if dto.quantity is not None:
            comp.quantity = dto.quantity
        if dto.manufacturer is not None:
            comp.manufacturer = dto.manufacturer
        if dto.hs_code is not None:
            comp.hs_code = dto.hs_code
        if dto.notes is not None:
            comp.notes = dto.notes
        if dto.criticality is not None:
            comp.criticality = dto.criticality
        if dto.lead_time_days is not None:
            comp.lead_time_days = dto.lead_time_days

        if dto.country_code is not None:
            comp.country_code = dto.country_code.upper()
            country = await self.repo.get_country(comp.country_code)
            comp.country_risk = country.risk_factor if country else 0.5

        if dto.analog_status is not None:
            comp.analog_status = dto.analog_status.upper()
            comp.analog_availability = self.get_analog_avail_score(comp.analog_status)

        # Синхронизация данных отечественного аналога при их наличии
        if (
            dto.analog_name is not None
            or dto.analog_manufacturer is not None
            or dto.analog_cost_rub is not None
            or dto.commercial_offer_doc is not None
        ):
            if comp.analogs and len(comp.analogs) > 0:
                first_analog = comp.analogs[0]
                if dto.analog_name is not None:
                    first_analog.name = dto.analog_name
                if dto.analog_manufacturer is not None:
                    first_analog.manufacturer = dto.analog_manufacturer
                if dto.analog_cost_rub is not None:
                    first_analog.unit_cost_rub = dto.analog_cost_rub
                if dto.redesign_cost_rub is not None:
                    first_analog.redesign_cost_rub = dto.redesign_cost_rub
                if dto.lead_time_days is not None:
                    first_analog.lead_time_days = dto.lead_time_days
                if dto.commercial_offer_doc is not None:
                    first_analog.description = dto.commercial_offer_doc
                if dto.analog_status is not None:
                    first_analog.compatibility_status = dto.analog_status
            elif dto.analog_name or dto.analog_manufacturer:
                new_analog = Analog(
                    component_id=comp.id,
                    name=dto.analog_name or "Отечественный аналог",
                    manufacturer=dto.analog_manufacturer or "Предприятие в РФ/ЕАЭС",
                    country_code="RU",
                    unit_cost_rub=dto.analog_cost_rub or 0.0,
                    redesign_cost_rub=dto.redesign_cost_rub or 0.0,
                    lead_time_days=dto.lead_time_days or 28,
                    compatibility_score=1.0 if comp.analog_status == "FULL_COMPATIBLE" else 0.7,
                    compatibility_status=comp.analog_status or "FULL_COMPATIBLE",
                    description=dto.commercial_offer_doc or "",
                )
                await self.repo.create_analog(new_analog)
        elif dto.redesign_cost_rub is not None and comp.analogs:
            comp.analogs[0].redesign_cost_rub = dto.redesign_cost_rub

        comp.cfi_score = self.calculate_cfi(comp.criticality, comp.country_risk, comp.analog_availability)
        comp.is_chokepoint = comp.cfi_score >= 0.70

        return await self.repo.update_component(comp)

    async def delete_component(self, component_id: int) -> None:
        """Удаление компонента и его подузлов"""
        comp = await self.repo.get_component(component_id)
        if not comp:
            raise ComponentNotFoundError(f"Компонент с ID {component_id} не найден")
        await self.repo.delete_component(comp)

    async def add_analog(self, component_id: int, dto: CreateAnalogDTO) -> Analog:
        """Добавление аналога для узла"""
        comp = await self.repo.get_component(component_id)
        if not comp:
            raise ComponentNotFoundError(f"Компонент с ID {component_id} не найден")

        analog = Analog(
            component_id=component_id,
            name=dto.name,
            manufacturer=dto.manufacturer,
            country_code=dto.country_code.upper(),
            unit_cost_rub=dto.unit_cost_rub,
            redesign_cost_rub=dto.redesign_cost_rub,
            lead_time_days=dto.lead_time_days,
            compatibility_score=dto.compatibility_score,
            compatibility_status=dto.compatibility_status,
            description=dto.description,
        )
        return await self.repo.create_analog(analog)

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
        comp.country_risk = 0.0 if analog.country_code in ("RU", "BY") else 0.25
        comp.analog_availability = analog.compatibility_score
        comp.analog_status = "FULL_COMPATIBLE"
        comp.unit_cost_rub = analog.unit_cost_rub
        comp.lead_time_days = analog.lead_time_days

        new_cfi = self.calculate_cfi(comp.criticality, comp.country_risk, comp.analog_availability)
        comp.cfi_score = new_cfi
        comp.is_chokepoint = new_cfi >= 0.70

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
