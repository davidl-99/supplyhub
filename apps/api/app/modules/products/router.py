from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.products.dependencies import (
    AuthorizedProductCreate,
    AuthorizedProductDeactivate,
    AuthorizedProductList,
    AuthorizedProductRead,
    AuthorizedProductUpdate,
)
from app.modules.products.exceptions import (
    ProductOrganizationCannotSupplyError,
    ProductOrganizationInactiveError,
    ProductOrganizationNotFoundError,
    ProductSkuAlreadyExistsError,
)
from app.modules.products.schemas import (
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


@router.post(
    "/",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    data: AuthorizedProductCreate,
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
    except ProductOrganizationCannotSupplyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization cannot supply products",
        ) from error
    except ProductSkuAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product SKU already exists for this organization",
        ) from error

    return ProductRead.model_validate(product)


@router.get(
    "/",
    response_model=ProductListRead,
)
def list_products(
    session: DatabaseSession,
    filters: AuthorizedProductList,
) -> ProductListRead:
    service = ProductService(session)

    products, total = service.list_all(filters)

    return ProductListRead(
        items=[ProductRead.model_validate(product) for product in products],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get(
    "/{product_id}",
    response_model=ProductRead,
)
def get_product(
    product: AuthorizedProductRead,
) -> ProductRead:
    return ProductRead.model_validate(product)


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
)
def update_product(
    product: AuthorizedProductUpdate,
    data: ProductUpdate,
    session: DatabaseSession,
) -> ProductRead:
    service = ProductService(session)

    try:
        product = service.update(
            product=product,
            data=data,
        )
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
    product: AuthorizedProductDeactivate,
    session: DatabaseSession,
) -> ProductRead:
    service = ProductService(session)
    product = service.deactivate(product)

    return ProductRead.model_validate(product)
