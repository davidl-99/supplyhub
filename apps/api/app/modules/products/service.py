import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.product import Product
from app.modules.organizations.repository import OrganizationRepository
from app.modules.products.exceptions import (
    ProductOrganizationInactiveError,
    ProductOrganizationNotFoundError,
    ProductSkuAlreadyExistsError,
)
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreate


class ProductService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.product_repository = ProductRepository(session)
        self.organization_repository = OrganizationRepository(session)

    def create(self, data: ProductCreate) -> Product:
        organization = self.organization_repository.get_by_id(
            data.organization_id,
        )

        if organization is None:
            raise ProductOrganizationNotFoundError

        if not organization.is_active:
            raise ProductOrganizationInactiveError

        existing_product = (
            self.product_repository.get_by_organization_and_sku(
                organization_id=data.organization_id,
                sku=data.sku,
            )
        )

        if existing_product is not None:
            raise ProductSkuAlreadyExistsError

        product = Product(
            organization_id=data.organization_id,
            sku=data.sku,
            name=data.name,
            description=data.description,
            price=data.price,
            currency=data.currency,
        )

        self.product_repository.add(product)

        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise ProductSkuAlreadyExistsError from error

        self.session.refresh(product)

        return product

    def list_all(
        self,
        organization_id: uuid.UUID | None = None,
    ) -> list[Product]:
        return self.product_repository.list_all(organization_id)