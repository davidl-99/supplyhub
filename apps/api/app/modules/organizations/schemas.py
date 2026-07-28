import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

# OrganizationRead Representa la respuesta pública de la API.
class OrganizationRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )
    # from_attributes=True permite que Pydantic construya la respuesta 
    # leyendo los atributos de un objeto SQLAlchemy, como 
    # organization.id y organization.name