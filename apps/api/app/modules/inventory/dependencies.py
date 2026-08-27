import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.identity import User
from app.models.inventory import InventoryLevel, InventoryReservation
from app.modules.auth.dependencies import CurrentUser
from app.modules.authorization.permissions import Permission, role_has_permission
from app.modules.authorization.service import AuthorizationService
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    InventoryAdjustmentCreate,
    InventoryLevelListQuery,
    InventoryReservationCreate,
    InventoryReservationListQuery,
    StockMovementListQuery,
)
from app.modules.products.repository import ProductRepository
from app.modules.warehouses.repository import WarehouseRepository

DatabaseSession = Annotated[Session, Depends(get_db_session)]
InventoryLevelFilters = Annotated[InventoryLevelListQuery, Query()]
StockMovementFilters = Annotated[StockMovementListQuery, Query()]
InventoryReservationFilters = Annotated[InventoryReservationListQuery, Query()]


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


def authorize_inventory_reservation_create(
    data: InventoryReservationCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> InventoryReservationCreate:
    _authorize_inventory_write(
        session,
        current_user,
        data.warehouse_id,
        data.product_id,
        Permission.RESERVATION_CREATE,
    )
    return data


def authorize_inventory_reservation_list(
    filters: InventoryReservationFilters,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> InventoryReservationListQuery:
    _require_organization_permission(
        session,
        current_user,
        filters.organization_id,
        Permission.RESERVATION_READ,
    )
    return filters


def authorize_inventory_reservation_read(
    reservation_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> InventoryReservation:
    _authorize_reservation(
        session,
        current_user,
        reservation_id,
        Permission.RESERVATION_READ,
    )
    reservation = InventoryRepository(session).get_reservation(reservation_id)
    if reservation is None:
        raise _reservation_not_found()
    return reservation


def authorize_inventory_reservation_release(
    reservation_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> uuid.UUID:
    return _authorize_reservation(
        session,
        current_user,
        reservation_id,
        Permission.RESERVATION_RELEASE,
    )


def authorize_inventory_reservation_consume(
    reservation_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> uuid.UUID:
    return _authorize_reservation(
        session,
        current_user,
        reservation_id,
        Permission.RESERVATION_CONSUME,
    )


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
AuthorizedInventoryReservationCreate = Annotated[
    InventoryReservationCreate,
    Depends(authorize_inventory_reservation_create),
]
AuthorizedInventoryReservationList = Annotated[
    InventoryReservationListQuery,
    Depends(authorize_inventory_reservation_list),
]
AuthorizedInventoryReservation = Annotated[
    InventoryReservation,
    Depends(authorize_inventory_reservation_read),
]
AuthorizedInventoryReservationRelease = Annotated[
    uuid.UUID,
    Depends(authorize_inventory_reservation_release),
]
AuthorizedInventoryReservationConsume = Annotated[
    uuid.UUID,
    Depends(authorize_inventory_reservation_consume),
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


def _authorize_reservation(
    session: Session,
    current_user: User,
    reservation_id: uuid.UUID,
    permission: Permission,
) -> uuid.UUID:
    """Authorize an operation on a reservation without loading it.

    Ownership is resolved with a scalar query so that release and consume can
    take their own ``SELECT ... FOR UPDATE`` on a session that has never seen
    the reservation or its level. An unknown reservation and one owned by
    another organization raise the same ``404``.
    """
    organization_id = InventoryRepository(session).get_reservation_organization_id(
        reservation_id
    )
    if organization_id is None:
        raise _reservation_not_found()

    membership = AuthorizationService(session).get_active_membership(
        organization_id,
        current_user.id,
    )
    if membership is None:
        raise _reservation_not_found()
    if not role_has_permission(membership.role, permission):
        raise _not_enough_permissions()
    return reservation_id


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


def _reservation_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Inventory reservation not found",
    )
