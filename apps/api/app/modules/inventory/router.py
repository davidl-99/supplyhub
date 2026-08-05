import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.inventory.exceptions import (
    InsufficientAvailableInventoryError,
    InsufficientInventoryError,
    InventoryLevelNotFoundError,
    InventoryOrganizationMismatchError,
    InventoryProductInactiveError,
    InventoryProductNotFoundError,
    InventoryReservationNotActiveError,
    InventoryReservationNotFoundError,
    InventoryWarehouseInactiveError,
    InventoryWarehouseNotFoundError,
)
from app.modules.inventory.schemas import (
    InventoryAdjustmentCreate,
    InventoryAdjustmentRead,
    InventoryLevelListQuery,
    InventoryLevelListRead,
    InventoryLevelRead,
    InventoryReservationCreate,
    InventoryReservationListQuery,
    InventoryReservationListRead,
    InventoryReservationOperationRead,
    InventoryReservationRead,
    StockMovementListQuery,
    StockMovementListRead,
    StockMovementRead,
)
from app.modules.inventory.service import InventoryService

router = APIRouter(prefix="/inventory", tags=["Inventory"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]
InventoryFilters = Annotated[InventoryLevelListQuery, Query()]
StockMovementFilters = Annotated[StockMovementListQuery, Query()]
InventoryReservationFilters = Annotated[InventoryReservationListQuery, Query()]


@router.post(
    "/adjustments",
    response_model=InventoryAdjustmentRead,
    status_code=status.HTTP_201_CREATED,
)
def adjust_inventory(
    data: InventoryAdjustmentCreate,
    session: DatabaseSession,
) -> InventoryAdjustmentRead:
    service = InventoryService(session)

    try:
        level, movement = service.adjust(data)
    except InventoryProductNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found") from error
    except InventoryWarehouseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found") from error
    except InventoryProductInactiveError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "Product is inactive") from error
    except InventoryWarehouseInactiveError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Warehouse is inactive"
        ) from error
    except InventoryOrganizationMismatchError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Product and warehouse belong to different organizations",
        ) from error
    except InsufficientInventoryError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Inventory quantity cannot become negative",
        ) from error
    except InsufficientAvailableInventoryError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Insufficient available inventory",
        ) from error

    return InventoryAdjustmentRead(
        level=InventoryLevelRead.model_validate(level),
        movement=StockMovementRead.model_validate(movement),
    )


@router.get("/levels", response_model=InventoryLevelListRead)
def list_inventory_levels(
    session: DatabaseSession,
    filters: InventoryFilters,
) -> InventoryLevelListRead:
    levels, total = InventoryService(session).list_levels(filters)
    return InventoryLevelListRead(
        items=[InventoryLevelRead.model_validate(level) for level in levels],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get(
    "/levels/{warehouse_id}/{product_id}",
    response_model=InventoryLevelRead,
)
def get_inventory_level(
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    session: DatabaseSession,
) -> InventoryLevelRead:
    try:
        level = InventoryService(session).get_level(warehouse_id, product_id)
    except InventoryLevelNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Inventory level not found",
        ) from error
    return InventoryLevelRead.model_validate(level)


@router.get("/movements", response_model=StockMovementListRead)
def list_stock_movements(
    session: DatabaseSession,
    filters: StockMovementFilters,
) -> StockMovementListRead:
    movements, total = InventoryService(session).list_movements(filters)
    return StockMovementListRead(
        items=[StockMovementRead.model_validate(movement) for movement in movements],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.post(
    "/reservations",
    response_model=InventoryReservationOperationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_reservation(
    data: InventoryReservationCreate,
    session: DatabaseSession,
) -> InventoryReservationOperationRead:
    try:
        level, reservation = InventoryService(session).create_reservation(data)
    except InventoryProductNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found") from error
    except InventoryWarehouseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found") from error
    except InventoryLevelNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Inventory level not found",
        ) from error
    except InventoryProductInactiveError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "Product is inactive") from error
    except InventoryWarehouseInactiveError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Warehouse is inactive",
        ) from error
    except InventoryOrganizationMismatchError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Product and warehouse belong to different organizations",
        ) from error
    except InsufficientAvailableInventoryError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Insufficient available inventory",
        ) from error

    return InventoryReservationOperationRead(
        level=InventoryLevelRead.model_validate(level),
        reservation=InventoryReservationRead.model_validate(reservation),
    )


@router.get("/reservations", response_model=InventoryReservationListRead)
def list_inventory_reservations(
    session: DatabaseSession,
    filters: InventoryReservationFilters,
) -> InventoryReservationListRead:
    reservations, total = InventoryService(session).list_reservations(filters)
    return InventoryReservationListRead(
        items=[
            InventoryReservationRead.model_validate(reservation)
            for reservation in reservations
        ],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get(
    "/reservations/{reservation_id}",
    response_model=InventoryReservationRead,
)
def get_inventory_reservation(
    reservation_id: uuid.UUID,
    session: DatabaseSession,
) -> InventoryReservationRead:
    try:
        reservation = InventoryService(session).get_reservation(reservation_id)
    except InventoryReservationNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Inventory reservation not found",
        ) from error
    return InventoryReservationRead.model_validate(reservation)


@router.post(
    "/reservations/{reservation_id}/release",
    response_model=InventoryReservationOperationRead,
)
def release_inventory_reservation(
    reservation_id: uuid.UUID,
    session: DatabaseSession,
) -> InventoryReservationOperationRead:
    try:
        level, reservation = InventoryService(session).release_reservation(
            reservation_id
        )
    except InventoryReservationNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Inventory reservation not found",
        ) from error
    except InventoryReservationNotActiveError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Inventory reservation is not active",
        ) from error
    return InventoryReservationOperationRead(
        level=InventoryLevelRead.model_validate(level),
        reservation=InventoryReservationRead.model_validate(reservation),
    )


@router.post(
    "/reservations/{reservation_id}/consume",
    response_model=InventoryReservationOperationRead,
)
def consume_inventory_reservation(
    reservation_id: uuid.UUID,
    session: DatabaseSession,
) -> InventoryReservationOperationRead:
    try:
        level, reservation, movement = InventoryService(session).consume_reservation(
            reservation_id
        )
    except InventoryReservationNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Inventory reservation not found",
        ) from error
    except InventoryReservationNotActiveError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Inventory reservation is not active",
        ) from error
    return InventoryReservationOperationRead(
        level=InventoryLevelRead.model_validate(level),
        reservation=InventoryReservationRead.model_validate(reservation),
        movement=StockMovementRead.model_validate(movement),
    )
