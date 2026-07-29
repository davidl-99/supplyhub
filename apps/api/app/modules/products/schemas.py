import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    organization_id: uuid.UUID

    sku: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Z0-9][A-Z0-9._-]*$",
    )

    name: str = Field(
        min_length=2,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    price: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    currency: str = Field(
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )


class ProductRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    sku: str
    name: str
    description: str | None
    price: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )