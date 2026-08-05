import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.inventory import InventoryLevel, InventoryReservation, StockMovement


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

    def lock_level(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> InventoryLevel | None:
        statement = (
            select(InventoryLevel)
            .where(
                InventoryLevel.warehouse_id == warehouse_id,
                InventoryLevel.product_id == product_id,
            )
            .with_for_update()
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

    def list_movements(
        self,
        inventory_level_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[StockMovement], int]:
        conditions = []

        if inventory_level_id is not None:
            conditions.append(StockMovement.inventory_level_id == inventory_level_id)
        if warehouse_id is not None:
            conditions.append(InventoryLevel.warehouse_id == warehouse_id)
        if product_id is not None:
            conditions.append(InventoryLevel.product_id == product_id)
        if created_from is not None:
            conditions.append(StockMovement.created_at >= created_from)
        if created_to is not None:
            conditions.append(StockMovement.created_at <= created_to)

        requires_level_join = warehouse_id is not None or product_id is not None
        count_statement = select(func.count()).select_from(StockMovement)
        statement = select(StockMovement)

        if requires_level_join:
            count_statement = count_statement.join(InventoryLevel)
            statement = statement.join(InventoryLevel)

        total = self.session.scalar(count_statement.where(*conditions)) or 0
        statement = (
            statement.where(*conditions)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .offset(offset)
            .limit(limit)
        )
        movements = list(self.session.scalars(statement).all())
        return movements, total

    def add_reservation(self, reservation: InventoryReservation) -> None:
        self.session.add(reservation)

    def get_reservation(
        self,
        reservation_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> InventoryReservation | None:
        statement = select(InventoryReservation).where(
            InventoryReservation.id == reservation_id
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def lock_level_by_id(self, inventory_level_id: uuid.UUID) -> InventoryLevel | None:
        statement = (
            select(InventoryLevel)
            .where(InventoryLevel.id == inventory_level_id)
            .with_for_update()
        )
        return self.session.scalar(statement)

    def list_reservations(
        self,
        inventory_level_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[InventoryReservation], int]:
        conditions = []

        if inventory_level_id is not None:
            conditions.append(
                InventoryReservation.inventory_level_id == inventory_level_id
            )
        if warehouse_id is not None:
            conditions.append(InventoryLevel.warehouse_id == warehouse_id)
        if product_id is not None:
            conditions.append(InventoryLevel.product_id == product_id)
        if status is not None:
            conditions.append(InventoryReservation.status == status)

        requires_level_join = warehouse_id is not None or product_id is not None
        count_statement = select(func.count()).select_from(InventoryReservation)
        statement = select(InventoryReservation)

        if requires_level_join:
            count_statement = count_statement.join(InventoryLevel)
            statement = statement.join(InventoryLevel)

        total = self.session.scalar(count_statement.where(*conditions)) or 0
        statement = (
            statement.where(*conditions)
            .order_by(
                InventoryReservation.created_at.desc(),
                InventoryReservation.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        reservations = list(self.session.scalars(statement).all())
        return reservations, total
