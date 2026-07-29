import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(
        self,
        product_id: uuid.UUID,
    ) -> Product | None:
        return self.session.get(
            Product,
            product_id,
        )

    def get_by_organization_and_sku(
        self,
        organization_id: uuid.UUID,
        sku: str,
    ) -> Product | None:
        statement = select(Product).where(
            Product.organization_id == organization_id,
            Product.sku == sku,
        )

        return self.session.scalar(statement)

    def list_all(
        self,
        organization_id: uuid.UUID | None = None,
    ) -> list[Product]:
        statement = select(Product)

        if organization_id is not None:
            statement = statement.where(
                Product.organization_id == organization_id,
            )

        statement = statement.order_by(
            Product.created_at.desc(),
        )

        return list(self.session.scalars(statement).all())

    def add(self, product: Product) -> None:
        self.session.add(product)