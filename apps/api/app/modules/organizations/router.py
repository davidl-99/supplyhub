from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.organizations.exceptions import (
    OrganizationSlugAlreadyExistsError,
)
from app.modules.organizations.schemas import (
    OrganizationCreate,
    OrganizationRead,
)
from app.modules.organizations.service import OrganizationService


router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)

# le indica a FastAPI: Antes de ejecutar el endpoint, crea una 
# sesión usando get_db_session() y entrégala en el parámetro session.
DatabaseSession = Annotated[
    Session,
    Depends(get_db_session),
]


@router.post(
    "/",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    data: OrganizationCreate,
    session: DatabaseSession,
) -> OrganizationRead:
    service = OrganizationService(session)

    try:
        organization = service.create(data)
    except OrganizationSlugAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        ) from error

    return OrganizationRead.model_validate(organization)


@router.get(
    "/",
    response_model=list[OrganizationRead],
)
def list_organizations(
    session: DatabaseSession,
) -> list[OrganizationRead]:
    service = OrganizationService(session)
    organizations = service.list_all()

    return [
        OrganizationRead.model_validate(organization)
        for organization in organizations
    ]