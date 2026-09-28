import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.identity import OrganizationMembership
from app.modules.auth.dependencies import CurrentUser
from app.modules.authorization.dependencies import require_permission
from app.modules.authorization.permissions import Permission
from app.modules.identity.service import IdentityService
from app.modules.organizations.exceptions import (
    OrganizationNotFoundError,
    OrganizationSlugAlreadyExistsError,
    OrganizationTypeCannotBeNarrowedError,
)
from app.modules.organizations.schemas import (
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
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
OrganizationReader = Annotated[
    OrganizationMembership,
    Depends(require_permission(Permission.ORGANIZATION_READ)),
]
OrganizationUpdater = Annotated[
    OrganizationMembership,
    Depends(require_permission(Permission.ORGANIZATION_UPDATE)),
]
OrganizationDeactivator = Annotated[
    OrganizationMembership,
    Depends(require_permission(Permission.ORGANIZATION_DEACTIVATE)),
]


@router.post(
    "/",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    data: OrganizationCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> OrganizationRead:
    """Onboard a new tenant, making the caller its first administrator.

    Authentication is the only requirement: there is no organization yet to
    hold a membership in. This creates a new tenant and never grants access to
    an existing one. See ADR 0006.
    """
    service = IdentityService(session)

    try:
        organization = service.create_organization_with_first_admin(
            current_user,
            data,
        )
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
    current_user: CurrentUser,
    session: DatabaseSession,
) -> list[OrganizationRead]:
    service = OrganizationService(session)
    organizations = service.list_for_user(current_user.id)

    return [
        OrganizationRead.model_validate(organization) for organization in organizations
    ]


@router.get(
    "/{organization_id}",
    response_model=OrganizationRead,
)
def get_organization(
    organization_id: uuid.UUID,
    session: DatabaseSession,
    _authorized_membership: OrganizationReader,
) -> OrganizationRead:
    service = OrganizationService(session)

    try:
        organization = service.get_by_id(organization_id)
    except OrganizationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        ) from error

    return OrganizationRead.model_validate(organization)


@router.patch(
    "/{organization_id}",
    response_model=OrganizationRead,
)
def update_organization(
    organization_id: uuid.UUID,
    data: OrganizationUpdate,
    session: DatabaseSession,
    _authorized_membership: OrganizationUpdater,
) -> OrganizationRead:
    service = OrganizationService(session)

    try:
        organization = service.update(
            organization_id=organization_id,
            data=data,
        )
    except OrganizationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        ) from error
    except OrganizationSlugAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        ) from error
    except OrganizationTypeCannotBeNarrowedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization type can only be expanded to both",
        ) from error

    return OrganizationRead.model_validate(organization)


@router.post(
    "/{organization_id}/deactivate",
    response_model=OrganizationRead,
)
def deactivate_organization(
    organization_id: uuid.UUID,
    session: DatabaseSession,
    _authorized_membership: OrganizationDeactivator,
) -> OrganizationRead:
    service = OrganizationService(session)

    try:
        organization = service.deactivate(organization_id)
    except OrganizationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        ) from error

    return OrganizationRead.model_validate(organization)
