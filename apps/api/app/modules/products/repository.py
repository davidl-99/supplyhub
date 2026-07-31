import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
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
        search: str | None = None,
        is_active: bool | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Product], int]:
        conditions = []

        if organization_id is not None:
            conditions.append(
                Product.organization_id == organization_id
            )

        if search is not None:
            search_pattern = f"%{search}%"

            conditions.append(
                or_(
                    Product.name.ilike(search_pattern),
                    Product.sku.ilike(search_pattern),
                    Product.description.ilike(search_pattern),
                )
            )

        if is_active is not None:
            conditions.append(
                Product.is_active == is_active
            )

        if min_price is not None:
            conditions.append(
                Product.price >= min_price
            )

        if max_price is not None:
            conditions.append(
                Product.price <= max_price
            )

        count_statement = (
            select(func.count())
            .select_from(Product)
            .where(*conditions)
        )

        total = self.session.scalar(count_statement) or 0

        statement = (
            select(Product)
            .where(*conditions)
            .order_by(
                Product.created_at.desc(),
                Product.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        products = list(
            self.session.scalars(statement).all()
        )

        return products, total

    def add(self, product: Product) -> None:
        self.session.add(product)