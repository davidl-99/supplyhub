import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.warehouses.exceptions import (
    WarehouseCodeAlreadyExistsError,
    WarehouseNotFoundError,
    WarehouseOrganizationCannotSupplyError,
    WarehouseOrganizationInactiveError,
    WarehouseOrganizationNotFoundError,
)
from app.modules.warehouses.schemas import (
    WarehouseCreate,
    WarehouseListQuery,
    WarehouseListRead,
    WarehouseRead,
    WarehouseUpdate,
)
from app.modules.warehouses.service import WarehouseService

router = APIRouter(prefix="/warehouses", tags=["Warehouses"])

DatabaseSession = Annotated[Session, Depends(get_db_session)]
WarehouseFilters = Annotated[WarehouseListQuery, Query()]


@router.post("/", response_model=WarehouseRead, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    data: WarehouseCreate,
    session: DatabaseSession,
) -> WarehouseRead:
    service = WarehouseService(session)

    try:
        warehouse = service.create(data)
    except WarehouseOrganizationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        ) from error
    except WarehouseOrganizationInactiveError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization is inactive",
        ) from error
    except WarehouseOrganizationCannotSupplyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization cannot manage warehouses",
        ) from error
    except WarehouseCodeAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Warehouse code already exists for this organization",
        ) from error

    return WarehouseRead.model_validate(warehouse)


@router.get("/", response_model=WarehouseListRead)
def list_warehouses(
    session: DatabaseSession,
    filters: WarehouseFilters,
) -> WarehouseListRead:
    warehouses, total = WarehouseService(session).list_all(filters)
    return WarehouseListRead(
        items=[WarehouseRead.model_validate(item) for item in warehouses],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{warehouse_id}", response_model=WarehouseRead)
def get_warehouse(
    warehouse_id: uuid.UUID,
    session: DatabaseSession,
) -> WarehouseRead:
    try:
        warehouse = WarehouseService(session).get_by_id(warehouse_id)
    except WarehouseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        ) from error

    return WarehouseRead.model_validate(warehouse)


@router.patch("/{warehouse_id}", response_model=WarehouseRead)
def update_warehouse(
    warehouse_id: uuid.UUID,
    data: WarehouseUpdate,
    session: DatabaseSession,
) -> WarehouseRead:
    try:
        warehouse = WarehouseService(session).update(warehouse_id, data)
    except WarehouseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        ) from error
    except WarehouseCodeAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Warehouse code already exists for this organization",
        ) from error

    return WarehouseRead.model_validate(warehouse)


@router.post("/{warehouse_id}/deactivate", response_model=WarehouseRead)
def deactivate_warehouse(
    warehouse_id: uuid.UUID,
    session: DatabaseSession,
) -> WarehouseRead:
    try:
        warehouse = WarehouseService(session).deactivate(warehouse_id)
    except WarehouseNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        ) from error

    return WarehouseRead.model_validate(warehouse)
