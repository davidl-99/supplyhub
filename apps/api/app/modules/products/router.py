import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.products.exceptions import (
    ProductOrganizationInactiveError,
    ProductOrganizationNotFoundError,
    ProductSkuAlreadyExistsError,
)
from app.modules.products.schemas import ProductCreate, ProductRead
from app.modules.products.service import ProductService


router = APIRouter(
    prefix="/products",
    tags=["Products"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db_session),
]


@router.post(
    "/",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    data: ProductCreate,
    session: DatabaseSession,
) -> ProductRead:
    service = ProductService(session)

    try:
        product = service.create(data)
    except ProductOrganizationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        ) from error
    except ProductOrganizationInactiveError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization is inactive",
        ) from error
    except ProductSkuAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product SKU already exists for this organization",
        ) from error

    return ProductRead.model_validate(product)


@router.get(
    "/",
    response_model=list[ProductRead],
)
def list_products(
    session: DatabaseSession,
    organization_id: uuid.UUID | None = None,
) -> list[ProductRead]:
    service = ProductService(session)
    products = service.list_all(organization_id)

    return [
        ProductRead.model_validate(product)
        for product in products
    ]