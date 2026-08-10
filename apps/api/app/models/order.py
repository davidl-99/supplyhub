import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint(
            "buyer_organization_id <> supplier_organization_id",
            name="ck_orders_organizations_different",
        ),
        CheckConstraint(
            "status IN ('draft', 'placed', 'cancelled', 'fulfilled')",
            name="ck_orders_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    buyer_organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier_organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    placed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OrderLine.id",
    )

    @property
    def total(self) -> Decimal:
        return sum((line.line_total for line in self.lines), start=Decimal("0.00"))


class OrderLine(Base):
    __tablename__ = "order_lines"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "product_id",
            "warehouse_id",
            name="uq_order_lines_order_product_warehouse",
        ),
        CheckConstraint("quantity > 0", name="ck_order_lines_quantity_positive"),
        CheckConstraint(
            "unit_price >= 0", name="ck_order_lines_unit_price_non_negative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("inventory_reservations.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    product_sku: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    order: Mapped[Order] = relationship(back_populates="lines")

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity
