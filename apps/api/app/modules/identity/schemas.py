import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

MembershipRole = Literal[
    "organization_admin",
    "catalog_manager",
    "warehouse_operator",
    "buyer",
    "viewer",
]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=12, max_length=128)

    model_config = ConfigDict(str_strip_whitespace=True)


class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MembershipCreate(BaseModel):
    user_id: uuid.UUID
    role: MembershipRole


class MembershipUpdate(BaseModel):
    role: MembershipRole | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if self.role is None:
            raise ValueError("Update fields cannot be null")
        return self


class MembershipRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: MembershipRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MembershipListQuery(BaseModel):
    role: MembershipRole | None = None
    is_active: bool | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class MembershipListRead(BaseModel):
    items: list[MembershipRead]
    total: int
    limit: int
    offset: int
