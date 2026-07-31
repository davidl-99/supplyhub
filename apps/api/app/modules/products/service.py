import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.product import Product
from app.modules.organizations.repository import OrganizationRepository
from app.modules.products.exceptions import (
    ProductNotFoundError,
    ProductOrganizationInactiveError,
    ProductOrganizationNotFoundError,
    ProductSkuAlreadyExistsError,
)
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import (
    ProductCreate,
    ProductListQuery,
    ProductUpdate,
)


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

        existing_product = self.product_repository.get_by_organization_and_sku(
            organization_id=data.organization_id,
            sku=data.sku,
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
        self._commit()
        self.session.refresh(product)

        return product

    def get_by_id(
        self,
        product_id: uuid.UUID,
    ) -> Product:
        product = self.product_repository.get_by_id(product_id)

        if product is None:
            raise ProductNotFoundError

        return product

    def list_all(
        self,
        filters: ProductListQuery,
    ) -> tuple[list[Product], int]:
        return self.product_repository.list_all(
            organization_id=filters.organization_id,
            search=filters.search,
            is_active=filters.is_active,
            min_price=filters.min_price,
            max_price=filters.max_price,
            limit=filters.limit,
            offset=filters.offset,
        )

    def update(
        self,
        product_id: uuid.UUID,
        data: ProductUpdate,
    ) -> Product:
        product = self.get_by_id(product_id)
        changes = data.model_dump(exclude_unset=True)

        new_sku = changes.get("sku")

        if new_sku is not None and new_sku != product.sku:
            existing_product = self.product_repository.get_by_organization_and_sku(
                organization_id=product.organization_id,
                sku=new_sku,
            )

            if existing_product is not None:
                raise ProductSkuAlreadyExistsError

        for field_name, value in changes.items():
            setattr(product, field_name, value)

        self._commit()
        self.session.refresh(product)

        return product

    def deactivate(
        self,
        product_id: uuid.UUID,
    ) -> Product:
        product = self.get_by_id(product_id)

        if not product.is_active:
            return product

        product.is_active = False

        self._commit()
        self.session.refresh(product)

        return product

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise ProductSkuAlreadyExistsError from error
