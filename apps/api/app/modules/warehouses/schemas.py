import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WarehouseCreate(BaseModel):
    organization_id: uuid.UUID
    code: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Z0-9][A-Z0-9._-]*$",
    )
    name: str = Field(min_length=2, max_length=150)
    address: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True)


class WarehouseUpdate(BaseModel):
    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        pattern=r"^[A-Z0-9][A-Z0-9._-]*$",
    )
    name: str | None = Field(default=None, min_length=2, max_length=150)
    address: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_update_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        for field_name in {"code", "name"}:
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"{field_name} cannot be null")

        return self


class WarehouseRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    name: str
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WarehouseListQuery(BaseModel):
    organization_id: uuid.UUID | None = None
    search: str | None = Field(default=None, min_length=1, max_length=150)
    is_active: bool | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )


class WarehouseListRead(BaseModel):
    items: list[WarehouseRead]
    total: int
    limit: int
    offset: int
