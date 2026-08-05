import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


# OrganizationCreate representa los datos que el cliente debe enviar:
# {
#   "name": "Acme Corporation",
#   "slug": "acme-corporation"
# }
class OrganizationCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=150,
    )

    slug: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )

    organization_type: Literal["supplier", "buyer", "both"] = "supplier"

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )


# El esquema permite enviar únicamente los campos que queremos modificar.
# por ejemplo:
# {
#   "name": "Acme Global Corporation"
# }
class OrganizationUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )

    slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )

    organization_type: Literal["supplier", "buyer", "both"] | None = None

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    # esto ejecuta una validación después de que Pydantic haya procesado los campos.
    @model_validator(mode="after")
    def validate_update_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError("Update fields cannot be null")

        return self


# OrganizationRead Representa la respuesta pública de la API.
class OrganizationRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    organization_type: Literal["supplier", "buyer", "both"]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )
    # from_attributes=True permite que Pydantic construya la respuesta
    # leyendo los atributos de un objeto SQLAlchemy, como
    # organization.id y organization.name
