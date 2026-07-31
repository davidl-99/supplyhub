import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.products.exceptions import (
    ProductNotFoundError,
    ProductOrganizationInactiveError,
    ProductOrganizationNotFoundError,
    ProductSkuAlreadyExistsError,
)
from app.modules.products.schemas import (
    ProductCreate,
    ProductListQuery,
    ProductListRead,
    ProductRead,
    ProductUpdate,
)
from app.modules.products.service import ProductService


router = APIRouter(
    prefix="/products",
    tags=["Products"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db_session),
]

ProductFilters = Annotated[
    ProductListQuery,
    Query(),
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
@router.get(
    "/",
    response_model=ProductListRead,
)
def list_products(
    session: DatabaseSession,
    filters: ProductFilters,
) -> ProductListRead:
    service = ProductService(session)

    products, total = service.list_all(filters)

    return ProductListRead(
        items=[
            ProductRead.model_validate(product)
            for product in products
        ],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get(
    "/{product_id}",
    response_model=ProductRead,
)
def get_product(
    product_id: uuid.UUID,
    session: DatabaseSession,
) -> ProductRead:
    service = ProductService(session)

    try:
        product = service.get_by_id(product_id)
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        ) from error

    return ProductRead.model_validate(product)


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
)
def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    session: DatabaseSession,
) -> ProductRead:
    service = ProductService(session)

    try:
        product = service.update(
            product_id=product_id,
            data=data,
        )
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        ) from error
    except ProductSkuAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product SKU already exists for this organization",
        ) from error

    return ProductRead.model_validate(product)


@router.post(
    "/{product_id}/deactivate",
    response_model=ProductRead,
)
def deactivate_product(
    product_id: uuid.UUID,
    session: DatabaseSession,
) -> ProductRead:
    service = ProductService(session)

    try:
        product = service.deactivate(product_id)
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        ) from error

    return ProductRead.model_validate(product)