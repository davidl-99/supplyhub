import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InventoryAdjustmentCreate(BaseModel):
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity_delta: int
    reason: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("quantity_delta")
    @classmethod
    def validate_quantity_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("quantity_delta cannot be zero")
        return value


class InventoryLevelRead(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StockMovementRead(BaseModel):
    id: uuid.UUID
    inventory_level_id: uuid.UUID
    quantity_delta: int
    resulting_quantity: int
    reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryAdjustmentRead(BaseModel):
    level: InventoryLevelRead
    movement: StockMovementRead


class InventoryLevelListQuery(BaseModel):
    warehouse_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class InventoryLevelListRead(BaseModel):
    items: list[InventoryLevelRead]
    total: int
    limit: int
    offset: int
