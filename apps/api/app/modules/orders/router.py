import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.orders.exceptions import (
    OrderBuyerCannotBuyError,
    OrderCannotCancelError,
    OrderCurrencyMismatchError,
    OrderError,
    OrderInsufficientInventoryError,
    OrderNotDraftError,
    OrderNotFoundError,
    OrderNotPlacedError,
    OrderOrganizationInactiveError,
    OrderOrganizationNotFoundError,
    OrderProductNotFoundError,
    OrderProductUnavailableError,
    OrderSupplierCannotSupplyError,
    OrderSupplierMismatchError,
    OrderWarehouseNotFoundError,
    OrderWarehouseUnavailableError,
)
from app.modules.orders.schemas import (
    OrderCreate,
    OrderListQuery,
    OrderListRead,
    OrderRead,
    OrderStatusEventRead,
    OrderStatusHistoryQuery,
    OrderStatusHistoryRead,
)
from app.modules.orders.service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]
OrderFilters = Annotated[OrderListQuery, Query()]
OrderHistoryFilters = Annotated[OrderStatusHistoryQuery, Query()]

ORDER_ERROR_RESPONSES: dict[type[OrderError], tuple[int, str]] = {
    OrderNotFoundError: (status.HTTP_404_NOT_FOUND, "Order not found"),
    OrderOrganizationNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "Buyer or supplier organization not found",
    ),
    OrderProductNotFoundError: (status.HTTP_404_NOT_FOUND, "Product not found"),
    OrderWarehouseNotFoundError: (status.HTTP_404_NOT_FOUND, "Warehouse not found"),
    OrderOrganizationInactiveError: (
        status.HTTP_409_CONFLICT,
        "Buyer and supplier organizations must be active",
    ),
    OrderBuyerCannotBuyError: (
        status.HTTP_409_CONFLICT,
        "Buyer organization cannot buy",
    ),
    OrderSupplierCannotSupplyError: (
        status.HTTP_409_CONFLICT,
        "Supplier organization cannot supply",
    ),
    OrderProductUnavailableError: (
        status.HTTP_409_CONFLICT,
        "Product is inactive",
    ),
    OrderWarehouseUnavailableError: (
        status.HTTP_409_CONFLICT,
        "Warehouse is inactive",
    ),
    OrderSupplierMismatchError: (
        status.HTTP_409_CONFLICT,
        "Products and warehouses must belong to the supplier organization",
    ),
    OrderCurrencyMismatchError: (
        status.HTTP_409_CONFLICT,
        "All order lines must use the same currency",
    ),
    OrderNotDraftError: (status.HTTP_409_CONFLICT, "Order is not a draft"),
    OrderNotPlacedError: (status.HTTP_409_CONFLICT, "Order is not placed"),
    OrderCannotCancelError: (
        status.HTTP_409_CONFLICT,
        "Fulfilled orders cannot be cancelled",
    ),
    OrderInsufficientInventoryError: (
        status.HTTP_409_CONFLICT,
        "Insufficient available inventory",
    ),
}


def raise_order_http_error(error: OrderError) -> NoReturn:
    status_code, detail = ORDER_ERROR_RESPONSES[type(error)]
    raise HTTPException(status_code=status_code, detail=detail) from error


@router.post("/", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, session: DatabaseSession) -> OrderRead:
    try:
        order = OrderService(session).create(data)
    except OrderError as error:
        raise_order_http_error(error)
    return OrderRead.model_validate(order)


@router.get("/", response_model=OrderListRead)
def list_orders(session: DatabaseSession, filters: OrderFilters) -> OrderListRead:
    orders, total = OrderService(session).list_all(filters)
    return OrderListRead(
        items=[OrderRead.model_validate(order) for order in orders],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: uuid.UUID, session: DatabaseSession) -> OrderRead:
    try:
        order = OrderService(session).get_by_id(order_id)
    except OrderError as error:
        raise_order_http_error(error)
    return OrderRead.model_validate(order)


@router.get("/{order_id}/history", response_model=OrderStatusHistoryRead)
def list_order_status_history(
    order_id: uuid.UUID,
    session: DatabaseSession,
    filters: OrderHistoryFilters,
) -> OrderStatusHistoryRead:
    try:
        events, total = OrderService(session).list_status_history(order_id, filters)
    except OrderError as error:
        raise_order_http_error(error)
    return OrderStatusHistoryRead(
        items=[OrderStatusEventRead.model_validate(event) for event in events],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.post("/{order_id}/place", response_model=OrderRead)
def place_order(order_id: uuid.UUID, session: DatabaseSession) -> OrderRead:
    try:
        order = OrderService(session).place(order_id)
    except OrderError as error:
        raise_order_http_error(error)
    return OrderRead.model_validate(order)


@router.post("/{order_id}/cancel", response_model=OrderRead)
def cancel_order(order_id: uuid.UUID, session: DatabaseSession) -> OrderRead:
    try:
        order = OrderService(session).cancel(order_id)
    except OrderError as error:
        raise_order_http_error(error)
    return OrderRead.model_validate(order)


@router.post("/{order_id}/fulfill", response_model=OrderRead)
def fulfill_order(order_id: uuid.UUID, session: DatabaseSession) -> OrderRead:
    try:
        order = OrderService(session).fulfill(order_id)
    except OrderError as error:
        raise_order_http_error(error)
    return OrderRead.model_validate(order)
