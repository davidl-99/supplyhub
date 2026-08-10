import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatusEvent


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, order: Order) -> None:
        self.session.add(order)

    def add_status_event(self, event: OrderStatusEvent) -> None:
        self.session.add(event)

    def get_by_id(
        self, order_id: uuid.UUID, *, for_update: bool = False
    ) -> Order | None:
        statement = select(Order).where(Order.id == order_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def list_all(
        self,
        buyer_organization_id: uuid.UUID | None = None,
        supplier_organization_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        conditions = []
        if buyer_organization_id is not None:
            conditions.append(Order.buyer_organization_id == buyer_organization_id)
        if supplier_organization_id is not None:
            conditions.append(
                Order.supplier_organization_id == supplier_organization_id
            )
        if status is not None:
            conditions.append(Order.status == status)

        total = (
            self.session.scalar(
                select(func.count()).select_from(Order).where(*conditions)
            )
            or 0
        )
        statement = (
            select(Order)
            .where(*conditions)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement).all()), total

    def list_status_events(
        self,
        order_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[OrderStatusEvent], int]:
        condition = OrderStatusEvent.order_id == order_id
        total = (
            self.session.scalar(
                select(func.count()).select_from(OrderStatusEvent).where(condition)
            )
            or 0
        )
        statement = (
            select(OrderStatusEvent)
            .where(condition)
            .order_by(OrderStatusEvent.created_at.asc(), OrderStatusEvent.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement).all()), total
