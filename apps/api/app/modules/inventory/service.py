import uuid

from sqlalchemy.orm import Session

from app.models.inventory import InventoryLevel, InventoryReservation, StockMovement
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


class InventoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.inventory_repository = InventoryRepository(session)
        self.product_repository = ProductRepository(session)
        self.warehouse_repository = WarehouseRepository(session)

    def adjust(
        self,
        data: InventoryAdjustmentCreate,
    ) -> tuple[InventoryLevel, StockMovement]:
        product = self.product_repository.get_by_id(data.product_id)
        if product is None:
            raise InventoryProductNotFoundError
        if not product.is_active:
            raise InventoryProductInactiveError

        warehouse = self.warehouse_repository.get_by_id(data.warehouse_id)
        if warehouse is None:
            raise InventoryWarehouseNotFoundError
        if not warehouse.is_active:
            raise InventoryWarehouseInactiveError

        if product.organization_id != warehouse.organization_id:
            raise InventoryOrganizationMismatchError

        level = self.inventory_repository.ensure_and_lock_level(
            warehouse_id=data.warehouse_id,
            product_id=data.product_id,
        )
        resulting_quantity = level.quantity + data.quantity_delta

        if resulting_quantity < 0:
            self.session.rollback()
            raise InsufficientInventoryError
        if resulting_quantity < level.reserved_quantity:
            self.session.rollback()
            raise InsufficientAvailableInventoryError

        level.quantity = resulting_quantity
        movement = StockMovement(
            inventory_level_id=level.id,
            quantity_delta=data.quantity_delta,
            resulting_quantity=resulting_quantity,
            reason=data.reason,
        )
        self.inventory_repository.add_movement(movement)
        self.session.commit()
        self.session.refresh(level)
        self.session.refresh(movement)
        return level, movement

    def get_level(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> InventoryLevel:
        level = self.inventory_repository.get_level(warehouse_id, product_id)
        if level is None:
            raise InventoryLevelNotFoundError
        return level

    def list_levels(
        self,
        filters: InventoryLevelListQuery,
    ) -> tuple[list[InventoryLevel], int]:
        return self.inventory_repository.list_levels(
            warehouse_id=filters.warehouse_id,
            product_id=filters.product_id,
            limit=filters.limit,
            offset=filters.offset,
        )

    def list_movements(
        self,
        filters: StockMovementListQuery,
    ) -> tuple[list[StockMovement], int]:
        return self.inventory_repository.list_movements(
            inventory_level_id=filters.inventory_level_id,
            warehouse_id=filters.warehouse_id,
            product_id=filters.product_id,
            created_from=filters.created_from,
            created_to=filters.created_to,
            limit=filters.limit,
            offset=filters.offset,
        )

    def create_reservation(
        self,
        data: InventoryReservationCreate,
    ) -> tuple[InventoryLevel, InventoryReservation]:
        product = self.product_repository.get_by_id(data.product_id)
        if product is None:
            raise InventoryProductNotFoundError
        if not product.is_active:
            raise InventoryProductInactiveError

        warehouse = self.warehouse_repository.get_by_id(data.warehouse_id)
        if warehouse is None:
            raise InventoryWarehouseNotFoundError
        if not warehouse.is_active:
            raise InventoryWarehouseInactiveError
        if product.organization_id != warehouse.organization_id:
            raise InventoryOrganizationMismatchError

        level = self.inventory_repository.lock_level(
            warehouse_id=data.warehouse_id,
            product_id=data.product_id,
        )
        if level is None:
            raise InventoryLevelNotFoundError
        if data.quantity > level.available_quantity:
            raise InsufficientAvailableInventoryError

        level.reserved_quantity += data.quantity
        reservation = InventoryReservation(
            inventory_level_id=level.id,
            quantity=data.quantity,
            external_reference=data.external_reference,
        )
        self.inventory_repository.add_reservation(reservation)
        self.session.commit()
        self.session.refresh(level)
        self.session.refresh(reservation)
        return level, reservation

    def get_reservation(self, reservation_id: uuid.UUID) -> InventoryReservation:
        reservation = self.inventory_repository.get_reservation(reservation_id)
        if reservation is None:
            raise InventoryReservationNotFoundError
        return reservation

    def list_reservations(
        self,
        filters: InventoryReservationListQuery,
    ) -> tuple[list[InventoryReservation], int]:
        return self.inventory_repository.list_reservations(
            inventory_level_id=filters.inventory_level_id,
            warehouse_id=filters.warehouse_id,
            product_id=filters.product_id,
            status=filters.status,
            limit=filters.limit,
            offset=filters.offset,
        )

    def release_reservation(
        self,
        reservation_id: uuid.UUID,
    ) -> tuple[InventoryLevel, InventoryReservation]:
        reservation = self._lock_active_reservation(reservation_id)
        level = self._lock_reservation_level(reservation)

        level.reserved_quantity -= reservation.quantity
        reservation.status = "released"
        self.session.commit()
        self.session.refresh(level)
        self.session.refresh(reservation)
        return level, reservation

    def consume_reservation(
        self,
        reservation_id: uuid.UUID,
    ) -> tuple[InventoryLevel, InventoryReservation, StockMovement]:
        reservation = self._lock_active_reservation(reservation_id)
        level = self._lock_reservation_level(reservation)

        level.quantity -= reservation.quantity
        level.reserved_quantity -= reservation.quantity
        reservation.status = "consumed"
        movement = StockMovement(
            inventory_level_id=level.id,
            quantity_delta=-reservation.quantity,
            resulting_quantity=level.quantity,
            reason=f"Consumed inventory reservation {reservation.id}",
        )
        self.inventory_repository.add_movement(movement)
        self.session.commit()
        self.session.refresh(level)
        self.session.refresh(reservation)
        self.session.refresh(movement)
        return level, reservation, movement

    def _lock_active_reservation(
        self,
        reservation_id: uuid.UUID,
    ) -> InventoryReservation:
        reservation = self.inventory_repository.get_reservation(
            reservation_id,
            for_update=True,
        )
        if reservation is None:
            raise InventoryReservationNotFoundError
        if reservation.status != "active":
            raise InventoryReservationNotActiveError
        return reservation

    def _lock_reservation_level(
        self,
        reservation: InventoryReservation,
    ) -> InventoryLevel:
        level = self.inventory_repository.lock_level_by_id(
            reservation.inventory_level_id
        )
        if level is None:
            raise RuntimeError("Reservation inventory level not found")
        return level
