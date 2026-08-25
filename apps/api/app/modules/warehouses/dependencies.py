import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.identity import User
from app.models.warehouse import Warehouse
from app.modules.auth.dependencies import CurrentUser
from app.modules.authorization.permissions import Permission, role_has_permission
from app.modules.authorization.service import AuthorizationService
from app.modules.warehouses.repository import WarehouseRepository
from app.modules.warehouses.schemas import WarehouseCreate, WarehouseListQuery

DatabaseSession = Annotated[Session, Depends(get_db_session)]
WarehouseFilters = Annotated[WarehouseListQuery, Query()]


def authorize_warehouse_create(
    data: WarehouseCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> WarehouseCreate:
    _require_organization_permission(
        session,
        current_user,
        data.organization_id,
        Permission.WAREHOUSE_CREATE,
    )
    return data


def authorize_warehouse_list(
    filters: WarehouseFilters,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> WarehouseListQuery:
    _require_organization_permission(
        session,
        current_user,
        filters.organization_id,
        Permission.WAREHOUSE_READ,
    )
    return filters


def authorize_warehouse_read(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Warehouse:
    return _get_authorized_warehouse(
        session,
        current_user,
        warehouse_id,
        Permission.WAREHOUSE_READ,
    )


def authorize_warehouse_update(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Warehouse:
    return _get_authorized_warehouse(
        session,
        current_user,
        warehouse_id,
        Permission.WAREHOUSE_UPDATE,
    )


def authorize_warehouse_deactivate(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Warehouse:
    return _get_authorized_warehouse(
        session,
        current_user,
        warehouse_id,
        Permission.WAREHOUSE_DEACTIVATE,
    )


AuthorizedWarehouseCreate = Annotated[
    WarehouseCreate,
    Depends(authorize_warehouse_create),
]
AuthorizedWarehouseList = Annotated[
    WarehouseListQuery,
    Depends(authorize_warehouse_list),
]
AuthorizedWarehouseRead = Annotated[
    Warehouse,
    Depends(authorize_warehouse_read),
]
AuthorizedWarehouseUpdate = Annotated[
    Warehouse,
    Depends(authorize_warehouse_update),
]
AuthorizedWarehouseDeactivate = Annotated[
    Warehouse,
    Depends(authorize_warehouse_deactivate),
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


def _get_authorized_warehouse(
    session: Session,
    current_user: User,
    warehouse_id: uuid.UUID,
    permission: Permission,
) -> Warehouse:
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return warehouse


def _warehouse_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Warehouse not found",
    )
