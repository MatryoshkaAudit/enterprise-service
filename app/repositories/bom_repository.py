from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from matryoshka_db.db_models import Product, Component, Analog, CountryRisk


class BOMRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_product(self, product_id: int) -> Product | None:
        query = select(Product).where(Product.id == product_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all_products(self) -> list[Product]:
        query = select(Product).order_by(Product.id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_product(self, product: Product) -> Product:
        self.session.add(product)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def get_product_components(self, product_id: int) -> list[Component]:
        query = (
            select(Component)
            .where(Component.product_id == product_id)
            .options(
                selectinload(Component.analogs),
                selectinload(Component.supplier),
            )
            .order_by(Component.tier, Component.id)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_component(self, component_id: int) -> Component | None:
        query = (
            select(Component)
            .where(Component.id == component_id)
            .options(selectinload(Component.analogs))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_component(self, component: Component) -> Component:
        self.session.add(component)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(component)
        return component

    async def update_component(self, component: Component) -> Component:
        await self.session.flush()
        await self.session.commit()
        return component

    async def delete_component(self, component: Component) -> None:
        await self.session.delete(component)
        await self.session.commit()

    async def get_analog(self, analog_id: int) -> Analog | None:
        query = select(Analog).where(Analog.id == analog_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_analog(self, analog: Analog) -> Analog:
        self.session.add(analog)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(analog)
        return analog

    async def get_all_countries(self) -> list[CountryRisk]:
        query = select(CountryRisk).order_by(CountryRisk.risk_factor, CountryRisk.country_name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_country(self, country_code: str) -> CountryRisk | None:
        query = select(CountryRisk).where(CountryRisk.country_code == country_code.upper())
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
