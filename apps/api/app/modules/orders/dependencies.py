import uuid
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.identity import User
from app.models.order import Order
from app.modules.auth.dependencies import CurrentUser
from app.modules.authorization.permissions import Permission, role_has_permission
from app.modules.authorization.service import AuthorizationService
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schemas import (
    OrderCreate,
    OrderListQuery,
    OrderStatusHistoryQuery,
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]
OrderFilters = Annotated[OrderListQuery, Query()]
OrderHistoryFilters = Annotated[OrderStatusHistoryQuery, Query()]

OrderParty = Literal["buyer", "supplier", "either"]


def authorize_order_create(
    data: OrderCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> OrderCreate:
    _require_organization_permission(
        session,
        current_user,
        data.buyer_organization_id,
        Permission.ORDER_CREATE,
    )
    return data


def authorize_order_list(
    filters: OrderFilters,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> OrderListQuery:
    provided_ids = tuple(
        organization_id
        for organization_id in (
            filters.buyer_organization_id,
            filters.supplier_organization_id,
        )
        if organization_id is not None
    )
    _require_any_organization_permission(
        session,
        current_user,
        provided_ids,
        Permission.ORDER_READ,
    )
    return filters


def authorize_order_read(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Order:
    return _get_authorized_order(
        session,
        current_user,
        order_id,
        Permission.ORDER_READ,
    )


def authorize_order_history(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> uuid.UUID:
    return _authorize_order(
        session,
        current_user,
        order_id,
        Permission.ORDER_READ,
        "either",
    )


def authorize_order_place(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> uuid.UUID:
    return _authorize_order(
        session,
        current_user,
        order_id,
        Permission.ORDER_PLACE,
        "buyer",
    )


def authorize_order_cancel(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> uuid.UUID:
    return _authorize_order(
        session,
        current_user,
        order_id,
        Permission.ORDER_CANCEL,
        "buyer",
    )


def authorize_order_fulfill(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> uuid.UUID:
    return _authorize_order(
        session,
        current_user,
        order_id,
        Permission.ORDER_FULFILL,
        "supplier",
    )


AuthorizedOrderCreate = Annotated[
    OrderCreate,
    Depends(authorize_order_create),
]
AuthorizedOrderList = Annotated[
    OrderListQuery,
    Depends(authorize_order_list),
]
AuthorizedOrderRead = Annotated[
    Order,
    Depends(authorize_order_read),
]
AuthorizedOrderHistory = Annotated[
    uuid.UUID,
    Depends(authorize_order_history),
]
AuthorizedOrderPlace = Annotated[
    uuid.UUID,
    Depends(authorize_order_place),
]
AuthorizedOrderCancel = Annotated[
    uuid.UUID,
    Depends(authorize_order_cancel),
]
AuthorizedOrderFulfill = Annotated[
    uuid.UUID,
    Depends(authorize_order_fulfill),
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


def _require_any_organization_permission(
    session: Session,
    current_user: User,
    organization_ids: tuple[uuid.UUID, ...],
    permission: Permission,
) -> None:
    """Authorize a collection route scoped by one or more organization filters.

    ``OrderRepository.list_all`` composes its filters with AND, so an active
    membership with the permission in any provided organization bounds the
    result to rows the caller is party to.
    """
    service = AuthorizationService(session)
    for organization_id in organization_ids:
        membership = service.get_membership_with_permission(
            organization_id,
            current_user.id,
            permission,
        )
        if membership is not None:
            return
    raise _not_enough_permissions()


def _get_authorized_order(
    session: Session,
    current_user: User,
    order_id: uuid.UUID,
    permission: Permission,
) -> Order:
    """Resolve an order the caller is allowed to read.

    Safe to materialize because no route using this resolver takes a row lock
    afterwards. Never reuse it for place, cancel, or fulfill.
    """
    order = OrderRepository(session).get_by_id(order_id)
    if order is None:
        raise _order_not_found()

    _require_order_party_permission(
        session,
        current_user,
        (order.buyer_organization_id, order.supplier_organization_id),
        permission,
        "either",
    )
    return order


def _authorize_order(
    session: Session,
    current_user: User,
    order_id: uuid.UUID,
    permission: Permission,
    party: OrderParty,
) -> uuid.UUID:
    """Authorize an operation on an order without loading it.

    The service re-reads the order with ``SELECT ... FOR UPDATE``; a dependency
    that materialized it would hand the service a stale, identity-mapped
    instance and silently defeat the lock.
    """
    parties = OrderRepository(session).get_party_organization_ids(order_id)
    if parties is None:
        raise _order_not_found()

    _require_order_party_permission(
        session,
        current_user,
        parties,
        permission,
        party,
    )
    return order_id


def _require_order_party_permission(
    session: Session,
    current_user: User,
    parties: tuple[uuid.UUID, uuid.UUID],
    permission: Permission,
    party: OrderParty,
) -> None:
    """Apply the party rule of a two-organization resource.

    A caller who is party to neither organization receives ``404`` so the
    response never confirms another tenant's order. A caller who is party to
    the order but on the wrong side, or whose role lacks the verb, receives
    ``403``: ownership is already established for both parties, so the
    response should distinguish vertical authorization from absence.
    """
    required_ids = _required_organization_ids(parties, party)
    counterparty_ids = tuple(
        organization_id
        for organization_id in parties
        if organization_id not in required_ids
    )

    service = AuthorizationService(session)
    is_party = False
    for organization_id in required_ids:
        membership = service.get_active_membership(organization_id, current_user.id)
        if membership is None:
            continue
        is_party = True
        if role_has_permission(membership.role, permission):
            return

    if not is_party and not any(
        service.get_active_membership(organization_id, current_user.id) is not None
        for organization_id in counterparty_ids
    ):
        raise _order_not_found()
    raise _not_enough_permissions()


def _required_organization_ids(
    parties: tuple[uuid.UUID, uuid.UUID],
    party: OrderParty,
) -> tuple[uuid.UUID, ...]:
    buyer_id, supplier_id = parties
    if party == "buyer":
        return (buyer_id,)
    if party == "supplier":
        return (supplier_id,)
    return (buyer_id, supplier_id)


def _not_enough_permissions() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )


def _order_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Order not found",
    )
