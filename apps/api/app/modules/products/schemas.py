import uuid
from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


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


class ProductUpdate(BaseModel):
    sku: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        pattern=r"^[A-Z0-9][A-Z0-9._-]*$",
    )

    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_update_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        non_nullable_fields = {
            "sku",
            "name",
            "price",
            "currency",
        }

        for field_name in non_nullable_fields:
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"{field_name} cannot be null")

        return self


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


class ProductListQuery(BaseModel):
    organization_id: uuid.UUID

    search: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    is_active: bool | None = None

    min_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    max_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    limit: int = Field(
        default=20,
        ge=1,
        le=100,
    )

    offset: int = Field(
        default=0,
        ge=0,
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    @model_validator(mode="after")
    def validate_price_range(self) -> Self:
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price cannot be greater than max_price")

        return self


class ProductListRead(BaseModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int
