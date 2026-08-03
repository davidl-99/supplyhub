import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.inventory import InventoryLevel, StockMovement


class InventoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_and_lock_level(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> InventoryLevel:
        statement = (
            insert(InventoryLevel)
            .values(
                id=uuid.uuid4(),
                warehouse_id=warehouse_id,
                product_id=product_id,
                quantity=0,
            )
            .on_conflict_do_nothing(
                constraint="uq_inventory_levels_warehouse_id_product_id"
            )
        )
        self.session.execute(statement)

        level_statement = (
            select(InventoryLevel)
            .where(
                InventoryLevel.warehouse_id == warehouse_id,
                InventoryLevel.product_id == product_id,
            )
            .with_for_update()
        )
        level = self.session.scalar(level_statement)

        if level is None:
            raise RuntimeError("Inventory level could not be initialized")

        return level

    def get_level(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> InventoryLevel | None:
        statement = select(InventoryLevel).where(
            InventoryLevel.warehouse_id == warehouse_id,
            InventoryLevel.product_id == product_id,
        )
        return self.session.scalar(statement)

    def list_levels(
        self,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[InventoryLevel], int]:
        conditions = []

        if warehouse_id is not None:
            conditions.append(InventoryLevel.warehouse_id == warehouse_id)
        if product_id is not None:
            conditions.append(InventoryLevel.product_id == product_id)

        count_statement = (
            select(func.count()).select_from(InventoryLevel).where(*conditions)
        )
        total = self.session.scalar(count_statement) or 0
        statement = (
            select(InventoryLevel)
            .where(*conditions)
            .order_by(InventoryLevel.updated_at.desc(), InventoryLevel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        levels = list(self.session.scalars(statement).all())
        return levels, total

    def add_movement(self, movement: StockMovement) -> None:
        self.session.add(movement)
