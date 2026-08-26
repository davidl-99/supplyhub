import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.identity import User
from app.models.inventory import InventoryLevel
from app.modules.auth.dependencies import CurrentUser
from app.modules.authorization.permissions import Permission, role_has_permission
from app.modules.authorization.service import AuthorizationService
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    InventoryAdjustmentCreate,
    InventoryLevelListQuery,
    StockMovementListQuery,
)
from app.modules.products.repository import ProductRepository
from app.modules.warehouses.repository import WarehouseRepository

DatabaseSession = Annotated[Session, Depends(get_db_session)]
InventoryLevelFilters = Annotated[InventoryLevelListQuery, Query()]
StockMovementFilters = Annotated[StockMovementListQuery, Query()]


def authorize_inventory_adjustment(
    data: InventoryAdjustmentCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> InventoryAdjustmentCreate:
    _authorize_inventory_write(
        session,
        current_user,
        data.warehouse_id,
        data.product_id,
        Permission.INVENTORY_ADJUST,
    )
    return data


def authorize_inventory_level_list(
    filters: InventoryLevelFilters,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> InventoryLevelListQuery:
    _require_organization_permission(
        session,
        current_user,
        filters.organization_id,
        Permission.INVENTORY_READ,
    )
    return filters


def authorize_inventory_level_read(
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> InventoryLevel:
    return _get_authorized_inventory_level(
        session,
        current_user,
        warehouse_id,
        product_id,
        Permission.INVENTORY_READ,
    )


def authorize_stock_movement_list(
    filters: StockMovementFilters,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> StockMovementListQuery:
    _require_organization_permission(
        session,
        current_user,
        filters.organization_id,
        Permission.INVENTORY_READ,
    )
    return filters


AuthorizedInventoryAdjustment = Annotated[
    InventoryAdjustmentCreate,
    Depends(authorize_inventory_adjustment),
]
AuthorizedInventoryLevelList = Annotated[
    InventoryLevelListQuery,
    Depends(authorize_inventory_level_list),
]
AuthorizedInventoryLevel = Annotated[
    InventoryLevel,
    Depends(authorize_inventory_level_read),
]
AuthorizedStockMovementList = Annotated[
    StockMovementListQuery,
    Depends(authorize_stock_movement_list),
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
        raise _not_enough_permissions()


def _authorize_inventory_write(
    session: Session,
    current_user: User,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    permission: Permission,
) -> None:
    """Authorize a write addressing a warehouse/product pair by UUID.

    The request body carries no organization scope, so an unknown warehouse
    and a warehouse belonging to another organization are both concealed as
    ``404``. The product is then required to belong to the same organization,
    which keeps a foreign product UUID indistinguishable from a missing one.
    """
    warehouse = WarehouseRepository(session).get_by_id(warehouse_id)
    if warehouse is None:
        raise _warehouse_not_found()

    membership = AuthorizationService(session).get_active_membership(
        warehouse.organization_id,
        current_user.id,
    )
    if membership is None:
        raise _warehouse_not_found()
    if not role_has_permission(membership.role, permission):
        raise _not_enough_permissions()

    product = ProductRepository(session).get_by_id(product_id)
    if product is None or product.organization_id != warehouse.organization_id:
        raise _product_not_found()


def _get_authorized_inventory_level(
    session: Session,
    current_user: User,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    permission: Permission,
) -> InventoryLevel:
    """Resolve an inventory level the caller is allowed to read.

    An unknown warehouse, a warehouse owned by another organization, and a
    pair without a stock row yet all raise the same ``404`` so the response
    never reveals which of the three happened.
    """
    warehouse = WarehouseRepository(session).get_by_id(warehouse_id)
    if warehouse is None:
        raise _inventory_level_not_found()

    membership = AuthorizationService(session).get_active_membership(
        warehouse.organization_id,
        current_user.id,
    )
    if membership is None:
        raise _inventory_level_not_found()
    if not role_has_permission(membership.role, permission):
        raise _not_enough_permissions()

    level = InventoryRepository(session).get_level(warehouse_id, product_id)
    if level is None:
        raise _inventory_level_not_found()
    return level


def _not_enough_permissions() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )


def _warehouse_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Warehouse not found",
    )


def _product_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Product not found",
    )


def _inventory_level_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Inventory level not found",
    )
