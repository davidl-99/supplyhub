import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderLineCreate(BaseModel):
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    buyer_organization_id: uuid.UUID
    supplier_organization_id: uuid.UUID
    lines: list[OrderLineCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.buyer_organization_id == self.supplier_organization_id:
            raise ValueError("Buyer and supplier organizations must differ")

        line_keys = {(line.product_id, line.warehouse_id) for line in self.lines}
        if len(line_keys) != len(self.lines):
            raise ValueError("Order lines must have unique product and warehouse pairs")
        return self


class OrderLineRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    reservation_id: uuid.UUID | None
    product_sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    currency: str
    line_total: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderRead(BaseModel):
    id: uuid.UUID
    buyer_organization_id: uuid.UUID
    supplier_organization_id: uuid.UUID
    status: Literal["draft", "placed", "cancelled", "fulfilled"]
    currency: str
    total: Decimal
    lines: list[OrderLineRead]
    created_at: datetime
    updated_at: datetime
    placed_at: datetime | None
    cancelled_at: datetime | None
    fulfilled_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OrderListQuery(BaseModel):
    buyer_organization_id: uuid.UUID | None = None
    supplier_organization_id: uuid.UUID | None = None
    status: Literal["draft", "placed", "cancelled", "fulfilled"] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class OrderListRead(BaseModel):
    items: list[OrderRead]
    total: int
    limit: int
    offset: int


class OrderStatusEventRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    from_status: Literal["draft", "placed", "cancelled", "fulfilled"] | None
    to_status: Literal["draft", "placed", "cancelled", "fulfilled"]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderStatusHistoryQuery(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class OrderStatusHistoryRead(BaseModel):
    items: list[OrderStatusEventRead]
    total: int
    limit: int
    offset: int
