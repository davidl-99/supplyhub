import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class StockMovementListQuery(BaseModel):
    inventory_level_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_created_range(self) -> "StockMovementListQuery":
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from cannot be greater than created_to")
        return self


class StockMovementListRead(BaseModel):
    items: list[StockMovementRead]
    total: int
    limit: int
    offset: int
