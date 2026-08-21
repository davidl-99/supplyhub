import uuid

from sqlalchemy.orm import Session

from app.models.identity import OrganizationMembership
from app.modules.authorization.permissions import Permission, role_has_permission
from app.modules.identity.repository import IdentityRepository


class AuthorizationService:
    def __init__(self, session: Session) -> None:
        self.repository = IdentityRepository(session)

    def get_active_membership(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> OrganizationMembership | None:
        membership = self.repository.get_membership_by_user(
            organization_id,
            user_id,
        )
        if membership is None or not membership.is_active:
            return None
        return membership

    def get_membership_with_permission(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        permission: Permission,
    ) -> OrganizationMembership | None:
        membership = self.get_active_membership(organization_id, user_id)
        if membership is None or not role_has_permission(membership.role, permission):
            return None
        return membership
