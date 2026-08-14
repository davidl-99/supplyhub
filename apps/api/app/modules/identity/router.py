import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.identity import OrganizationMembership
from app.modules.authorization.dependencies import require_permission
from app.modules.authorization.permissions import Permission
from app.modules.identity.exceptions import (
    IdentityError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
    MembershipOrganizationInactiveError,
    MembershipOrganizationNotFoundError,
    MembershipRoleIncompatibleError,
    UserEmailAlreadyExistsError,
    UserInactiveError,
    UserNotFoundError,
)
from app.modules.identity.schemas import (
    MembershipCreate,
    MembershipListQuery,
    MembershipListRead,
    MembershipRead,
    MembershipUpdate,
    UserCreate,
    UserRead,
)
from app.modules.identity.service import IdentityService

users_router = APIRouter(prefix="/users", tags=["Users"])
memberships_router = APIRouter(
    prefix="/organizations/{organization_id}/memberships",
    tags=["Memberships"],
)
DatabaseSession = Annotated[Session, Depends(get_db_session)]
MembershipFilters = Annotated[MembershipListQuery, Query()]
MembershipReader = Annotated[
    OrganizationMembership,
    Depends(require_permission(Permission.MEMBERSHIP_READ)),
]
MembershipCreator = Annotated[
    OrganizationMembership,
    Depends(require_permission(Permission.MEMBERSHIP_CREATE)),
]
MembershipUpdater = Annotated[
    OrganizationMembership,
    Depends(require_permission(Permission.MEMBERSHIP_UPDATE)),
]
MembershipDeactivator = Annotated[
    OrganizationMembership,
    Depends(require_permission(Permission.MEMBERSHIP_DEACTIVATE)),
]

IDENTITY_ERROR_RESPONSES: dict[type[IdentityError], tuple[int, str]] = {
    UserNotFoundError: (status.HTTP_404_NOT_FOUND, "User not found"),
    MembershipNotFoundError: (status.HTTP_404_NOT_FOUND, "Membership not found"),
    MembershipOrganizationNotFoundError: (
        status.HTTP_404_NOT_FOUND,
        "Organization not found",
    ),
    UserEmailAlreadyExistsError: (
        status.HTTP_409_CONFLICT,
        "User email already exists",
    ),
    MembershipAlreadyExistsError: (
        status.HTTP_409_CONFLICT,
        "User already has a membership in this organization",
    ),
    MembershipOrganizationInactiveError: (
        status.HTTP_409_CONFLICT,
        "Organization is inactive",
    ),
    UserInactiveError: (status.HTTP_409_CONFLICT, "User is inactive"),
    MembershipRoleIncompatibleError: (
        status.HTTP_409_CONFLICT,
        "Membership role is incompatible with the organization type",
    ),
}


def raise_identity_http_error(error: IdentityError) -> NoReturn:
    status_code, detail = IDENTITY_ERROR_RESPONSES[type(error)]
    raise HTTPException(status_code=status_code, detail=detail) from error


@users_router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, session: DatabaseSession) -> UserRead:
    try:
        user = IdentityService(session).create_user(data)
    except IdentityError as error:
        raise_identity_http_error(error)
    return UserRead.model_validate(user)


@users_router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: uuid.UUID, session: DatabaseSession) -> UserRead:
    try:
        user = IdentityService(session).get_user(user_id)
    except IdentityError as error:
        raise_identity_http_error(error)
    return UserRead.model_validate(user)


@memberships_router.post(
    "/",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def create_membership(
    organization_id: uuid.UUID,
    data: MembershipCreate,
    session: DatabaseSession,
    _authorized_membership: MembershipCreator,
) -> MembershipRead:
    try:
        membership = IdentityService(session).create_membership(organization_id, data)
    except IdentityError as error:
        raise_identity_http_error(error)
    return MembershipRead.model_validate(membership)


@memberships_router.get("/", response_model=MembershipListRead)
def list_memberships(
    organization_id: uuid.UUID,
    session: DatabaseSession,
    filters: MembershipFilters,
    _authorized_membership: MembershipReader,
) -> MembershipListRead:
    try:
        memberships, total = IdentityService(session).list_memberships(
            organization_id, filters
        )
    except IdentityError as error:
        raise_identity_http_error(error)
    return MembershipListRead(
        items=[MembershipRead.model_validate(item) for item in memberships],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@memberships_router.patch("/{membership_id}", response_model=MembershipRead)
def update_membership(
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    data: MembershipUpdate,
    session: DatabaseSession,
    _authorized_membership: MembershipUpdater,
) -> MembershipRead:
    try:
        membership = IdentityService(session).update_membership(
            organization_id, membership_id, data
        )
    except IdentityError as error:
        raise_identity_http_error(error)
    return MembershipRead.model_validate(membership)


@memberships_router.post(
    "/{membership_id}/deactivate",
    response_model=MembershipRead,
)
def deactivate_membership(
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    session: DatabaseSession,
    _authorized_membership: MembershipDeactivator,
) -> MembershipRead:
    try:
        membership = IdentityService(session).deactivate_membership(
            organization_id, membership_id
        )
    except IdentityError as error:
        raise_identity_http_error(error)
    return MembershipRead.model_validate(membership)
