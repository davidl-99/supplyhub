import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.inventory import InventoryReservation, StockMovement
from app.models.order import Order, OrderLine, OrderStatusEvent
from app.modules.inventory.repository import InventoryRepository
from app.modules.orders.exceptions import (
    OrderBuyerCannotBuyError,
    OrderCannotCancelError,
    OrderCurrencyMismatchError,
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
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schemas import (
    OrderCreate,
    OrderListQuery,
    OrderStatusHistoryQuery,
)
from app.modules.organizations.repository import OrganizationRepository
from app.modules.products.repository import ProductRepository
from app.modules.warehouses.repository import WarehouseRepository


class OrderService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.order_repository = OrderRepository(session)
        self.organization_repository = OrganizationRepository(session)
        self.product_repository = ProductRepository(session)
        self.warehouse_repository = WarehouseRepository(session)
        self.inventory_repository = InventoryRepository(session)

    def create(self, data: OrderCreate) -> Order:
        buyer = self.organization_repository.get_by_id(data.buyer_organization_id)
        supplier = self.organization_repository.get_by_id(data.supplier_organization_id)
        if buyer is None or supplier is None:
            raise OrderOrganizationNotFoundError
        if not buyer.is_active or not supplier.is_active:
            raise OrderOrganizationInactiveError
        if buyer.organization_type not in {"buyer", "both"}:
            raise OrderBuyerCannotBuyError
        if supplier.organization_type not in {"supplier", "both"}:
            raise OrderSupplierCannotSupplyError

        lines: list[OrderLine] = []
        currency: str | None = None
        for line_data in data.lines:
            product = self.product_repository.get_by_id(line_data.product_id)
            if product is None:
                raise OrderProductNotFoundError
            if not product.is_active:
                raise OrderProductUnavailableError
            warehouse = self.warehouse_repository.get_by_id(line_data.warehouse_id)
            if warehouse is None:
                raise OrderWarehouseNotFoundError
            if not warehouse.is_active:
                raise OrderWarehouseUnavailableError
            if (
                product.organization_id != supplier.id
                or warehouse.organization_id != supplier.id
            ):
                raise OrderSupplierMismatchError
            if currency is not None and product.currency != currency:
                raise OrderCurrencyMismatchError
            currency = product.currency
            lines.append(
                OrderLine(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    product_sku=product.sku,
                    product_name=product.name,
                    quantity=line_data.quantity,
                    unit_price=product.price,
                    currency=product.currency,
                )
            )

        if currency is None:
            raise RuntimeError("Order currency could not be determined")

        order = Order(
            buyer_organization_id=buyer.id,
            supplier_organization_id=supplier.id,
            currency=currency,
            lines=lines,
        )
        self.order_repository.add(order)
        self.session.flush()
        self._add_status_event(order.id, None, "draft")
        self.session.commit()
        self.session.refresh(order)
        return order

    def get_by_id(self, order_id: uuid.UUID) -> Order:
        order = self.order_repository.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError
        return order

    def list_all(self, filters: OrderListQuery) -> tuple[list[Order], int]:
        return self.order_repository.list_all(
            buyer_organization_id=filters.buyer_organization_id,
            supplier_organization_id=filters.supplier_organization_id,
            status=filters.status,
            limit=filters.limit,
            offset=filters.offset,
        )

    def list_status_history(
        self,
        order_id: uuid.UUID,
        filters: OrderStatusHistoryQuery,
    ) -> tuple[list[OrderStatusEvent], int]:
        self.get_by_id(order_id)
        return self.order_repository.list_status_events(
            order_id=order_id,
            limit=filters.limit,
            offset=filters.offset,
        )

    def place(self, order_id: uuid.UUID) -> Order:
        order = self._get_locked(order_id)
        if order.status != "draft":
            raise OrderNotDraftError

        for line in sorted(
            order.lines,
            key=lambda item: (item.warehouse_id, item.product_id),
        ):
            product = self.product_repository.get_by_id(line.product_id)
            warehouse = self.warehouse_repository.get_by_id(line.warehouse_id)
            if product is None:
                raise OrderProductNotFoundError
            if product.organization_id != order.supplier_organization_id:
                raise OrderSupplierMismatchError
            if not product.is_active:
                raise OrderProductUnavailableError
            if warehouse is None:
                raise OrderWarehouseNotFoundError
            if warehouse.organization_id != order.supplier_organization_id:
                raise OrderSupplierMismatchError
            if not warehouse.is_active:
                raise OrderWarehouseUnavailableError

            level = self.inventory_repository.lock_level(
                warehouse_id=line.warehouse_id,
                product_id=line.product_id,
            )
            if level is None or line.quantity > level.available_quantity:
                self.session.rollback()
                raise OrderInsufficientInventoryError

            level.reserved_quantity += line.quantity
            reservation = InventoryReservation(
                inventory_level_id=level.id,
                quantity=line.quantity,
                external_reference=f"order:{order.id}:line:{line.id}",
            )
            self.inventory_repository.add_reservation(reservation)
            self.session.flush()
            line.reservation_id = reservation.id

        order.status = "placed"
        order.placed_at = datetime.now(UTC)
        self._add_status_event(order.id, "draft", "placed")
        self.session.commit()
        self.session.refresh(order)
        return order

    def cancel(self, order_id: uuid.UUID) -> Order:
        order = self._get_locked(order_id)
        if order.status == "cancelled":
            return order

        if order.status == "fulfilled":
            raise OrderCannotCancelError

        if order.status == "placed":
            for line in order.lines:
                if line.reservation_id is None:
                    raise RuntimeError("Placed order line has no reservation")
                reservation = self.inventory_repository.get_reservation(
                    line.reservation_id,
                    for_update=True,
                )
                if reservation is None or reservation.status != "active":
                    raise RuntimeError("Placed order reservation is not active")
                level = self.inventory_repository.lock_level_by_id(
                    reservation.inventory_level_id
                )
                if level is None:
                    raise RuntimeError("Reservation inventory level not found")
                level.reserved_quantity -= reservation.quantity
                reservation.status = "released"

        previous_status = order.status
        order.status = "cancelled"
        order.cancelled_at = datetime.now(UTC)
        self._add_status_event(order.id, previous_status, "cancelled")
        self.session.commit()
        self.session.refresh(order)
        return order

    def fulfill(self, order_id: uuid.UUID) -> Order:
        order = self._get_locked(order_id)
        if order.status != "placed":
            raise OrderNotPlacedError

        for line in sorted(
            order.lines,
            key=lambda item: (item.warehouse_id, item.product_id),
        ):
            if line.reservation_id is None:
                raise RuntimeError("Placed order line has no reservation")
            reservation = self.inventory_repository.get_reservation(
                line.reservation_id,
                for_update=True,
            )
            if reservation is None or reservation.status != "active":
                raise RuntimeError("Placed order reservation is not active")
            level = self.inventory_repository.lock_level_by_id(
                reservation.inventory_level_id
            )
            if level is None:
                raise RuntimeError("Reservation inventory level not found")

            level.quantity -= reservation.quantity
            level.reserved_quantity -= reservation.quantity
            reservation.status = "consumed"
            self.inventory_repository.add_movement(
                StockMovement(
                    inventory_level_id=level.id,
                    quantity_delta=-reservation.quantity,
                    resulting_quantity=level.quantity,
                    reason=f"Fulfilled order {order.id} line {line.id}",
                )
            )

        order.status = "fulfilled"
        order.fulfilled_at = datetime.now(UTC)
        self._add_status_event(order.id, "placed", "fulfilled")
        self.session.commit()
        self.session.refresh(order)
        return order

    def _get_locked(self, order_id: uuid.UUID) -> Order:
        order = self.order_repository.get_by_id(order_id, for_update=True)
        if order is None:
            raise OrderNotFoundError
        return order

    def _add_status_event(
        self,
        order_id: uuid.UUID,
        from_status: str | None,
        to_status: str,
    ) -> None:
        self.order_repository.add_status_event(
            OrderStatusEvent(
                order_id=order_id,
                from_status=from_status,
                to_status=to_status,
                created_at=datetime.now(UTC),
            )
        )
