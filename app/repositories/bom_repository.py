from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from matryoshka_db.db_models import Product, Component, Analog


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

    async def get_analog(self, analog_id: int) -> Analog | None:
        query = select(Analog).where(Analog.id == analog_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_component(self, component: Component) -> Component:
        await self.session.flush()
        return component
