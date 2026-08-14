import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.identity import OrganizationMembership
from app.modules.auth.dependencies import CurrentUser
from app.modules.authorization.permissions import Permission, role_has_permission
from app.modules.identity.repository import IdentityRepository
from app.modules.organizations.repository import OrganizationRepository

DatabaseSession = Annotated[Session, Depends(get_db_session)]


def get_active_membership(
    organization_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> OrganizationMembership:
    membership = IdentityRepository(session).get_membership_by_user(
        organization_id,
        current_user.id,
    )
    if membership is None or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return membership


def get_locked_active_membership(
    organization_id: uuid.UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> OrganizationMembership:
    organization = OrganizationRepository(session).get_by_id(
        organization_id,
        for_update=True,
    )
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return get_active_membership(organization_id, current_user, session)


ActiveMembership = Annotated[
    OrganizationMembership,
    Depends(get_active_membership),
]


def require_permission(
    permission: Permission,
    *,
    lock_organization: bool = False,
) -> Callable[..., OrganizationMembership]:
    membership_dependency = (
        get_locked_active_membership if lock_organization else get_active_membership
    )

    def permission_dependency(
        membership: Annotated[
            OrganizationMembership,
            Depends(membership_dependency),
        ],
    ) -> OrganizationMembership:
        if not role_has_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return membership

    return permission_dependency
