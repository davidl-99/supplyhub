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


ActiveMembership = Annotated[
    OrganizationMembership,
    Depends(get_active_membership),
]


def require_permission(
    permission: Permission,
) -> Callable[..., OrganizationMembership]:
    def permission_dependency(
        membership: ActiveMembership,
    ) -> OrganizationMembership:
        if not role_has_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return membership

    return permission_dependency
