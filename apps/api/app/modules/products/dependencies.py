import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.identity import User
from app.models.product import Product
from app.modules.auth.dependencies import CurrentUser
from app.modules.authorization.permissions import Permission, role_has_permission
from app.modules.authorization.service import AuthorizationService
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreate, ProductListQuery

DatabaseSession = Annotated[Session, Depends(get_db_session)]
ProductFilters = Annotated[ProductListQuery, Query()]


def authorize_product_create(
    data: ProductCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ProductCreate:
    _require_organization_permission(
        session,
        current_user,
        data.organization_id,
        Permission.PRODUCT_CREATE,
    )
    return data


def authorize_product_list(
    filters: ProductFilters,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ProductListQuery:
    _require_organization_permission(
        session,
        current_user,
        filters.organization_id,
        Permission.PRODUCT_READ,
    )
    return filters


def authorize_product_read(
    product_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Product:
    return _get_authorized_product(
        session,
        current_user,
        product_id,
        Permission.PRODUCT_READ,
    )


def authorize_product_update(
    product_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Product:
    return _get_authorized_product(
        session,
        current_user,
        product_id,
        Permission.PRODUCT_UPDATE,
    )


def authorize_product_deactivate(
    product_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Product:
    return _get_authorized_product(
        session,
        current_user,
        product_id,
        Permission.PRODUCT_DEACTIVATE,
    )


AuthorizedProductCreate = Annotated[
    ProductCreate,
    Depends(authorize_product_create),
]
AuthorizedProductList = Annotated[
    ProductListQuery,
    Depends(authorize_product_list),
]
AuthorizedProductRead = Annotated[
    Product,
    Depends(authorize_product_read),
]
AuthorizedProductUpdate = Annotated[
    Product,
    Depends(authorize_product_update),
]
AuthorizedProductDeactivate = Annotated[
    Product,
    Depends(authorize_product_deactivate),
]


def _require_organization_permission(
    session: Session,
    current_user: User,
    organization_id: uuid.UUID,
    permission: Permission,
) -> None:
    membership = AuthorizationService(session).get_membership_with_permission(
        organization_id,
        current_user.id,
        permission,
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )


def _get_authorized_product(
    session: Session,
    current_user: User,
    product_id: uuid.UUID,
    permission: Permission,
) -> Product:
    product = ProductRepository(session).get_by_id(product_id)
    if product is None:
        raise _product_not_found()

    membership = AuthorizationService(session).get_active_membership(
        product.organization_id,
        current_user.id,
    )
    if membership is None:
        raise _product_not_found()
    if not role_has_permission(membership.role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return product


def _product_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Product not found",
    )
