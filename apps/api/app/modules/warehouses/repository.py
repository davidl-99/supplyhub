import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.warehouse import Warehouse


class WarehouseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, warehouse_id: uuid.UUID) -> Warehouse | None:
        return self.session.get(Warehouse, warehouse_id)

    def get_by_organization_and_code(
        self,
        organization_id: uuid.UUID,
        code: str,
    ) -> Warehouse | None:
        statement = select(Warehouse).where(
            Warehouse.organization_id == organization_id,
            Warehouse.code == code,
        )
        return self.session.scalar(statement)

    def list_all(
        self,
        organization_id: uuid.UUID | None = None,
        search: str | None = None,
        is_active: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Warehouse], int]:
        conditions = []

        if organization_id is not None:
            conditions.append(Warehouse.organization_id == organization_id)

        if search is not None:
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Warehouse.code.ilike(search_pattern),
                    Warehouse.name.ilike(search_pattern),
                    Warehouse.address.ilike(search_pattern),
                )
            )

        if is_active is not None:
            conditions.append(Warehouse.is_active == is_active)

        count_statement = select(func.count()).select_from(Warehouse).where(*conditions)
        total = self.session.scalar(count_statement) or 0

        statement = (
            select(Warehouse)
            .where(*conditions)
            .order_by(Warehouse.created_at.desc(), Warehouse.id.desc())
            .offset(offset)
            .limit(limit)
        )
        warehouses = list(self.session.scalars(statement).all())

        return warehouses, total

    def add(self, warehouse: Warehouse) -> None:
        self.session.add(warehouse)
