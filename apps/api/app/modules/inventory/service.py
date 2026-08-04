import uuid

from sqlalchemy.orm import Session

from app.models.inventory import InventoryLevel, StockMovement
from app.modules.inventory.exceptions import (
    InsufficientInventoryError,
    InventoryLevelNotFoundError,
    InventoryOrganizationMismatchError,
    InventoryProductInactiveError,
    InventoryProductNotFoundError,
    InventoryWarehouseInactiveError,
    InventoryWarehouseNotFoundError,
)
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    InventoryAdjustmentCreate,
    InventoryLevelListQuery,
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
