import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.identity import OrganizationMembership, User
from app.models.organization import Organization
from app.modules.identity.exceptions import (
    MembershipAlreadyExistsError,
    MembershipLastAdministratorError,
    MembershipNotFoundError,
    MembershipOrganizationInactiveError,
    MembershipOrganizationNotFoundError,
    MembershipRoleIncompatibleError,
    UserEmailAlreadyExistsError,
    UserInactiveError,
    UserNotFoundError,
)
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.roles import SUPPLIER_ROLES, MembershipRole
from app.modules.identity.schemas import (
    MembershipCreate,
    MembershipListQuery,
    MembershipUpdate,
    UserCreate,
)
from app.modules.organizations.repository import OrganizationRepository


class IdentityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IdentityRepository(session)
        self.organization_repository = OrganizationRepository(session)

    def create_user(self, data: UserCreate) -> User:
        normalized_email = str(data.email).lower()
        if self.repository.get_user_by_email(normalized_email) is not None:
            raise UserEmailAlreadyExistsError

        user = User(
            email=normalized_email,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
        )
        self.repository.add_user(user)
        self._commit(UserEmailAlreadyExistsError)
        self.session.refresh(user)
        return user

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.repository.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError
        return user

    def create_membership(
        self,
        organization_id: uuid.UUID,
        data: MembershipCreate,
    ) -> OrganizationMembership:
        organization = self._get_active_organization(organization_id)
        user = self.get_user(data.user_id)
        if not user.is_active:
            raise UserInactiveError
        if self.repository.get_membership_by_user(organization_id, user.id) is not None:
            raise MembershipAlreadyExistsError
        self._validate_role(organization, data.role)

        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=data.role,
        )
        self.repository.add_membership(membership)
        self._commit(MembershipAlreadyExistsError)
        self.session.refresh(membership)
        return membership

    def list_memberships(
        self,
        organization_id: uuid.UUID,
        filters: MembershipListQuery,
    ) -> tuple[list[OrganizationMembership], int]:
        self._get_organization(organization_id)
        return self.repository.list_memberships(
            organization_id=organization_id,
            role=filters.role,
            is_active=filters.is_active,
            limit=filters.limit,
            offset=filters.offset,
        )

    def update_membership(
        self,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID,
        data: MembershipUpdate,
    ) -> OrganizationMembership:
        organization = self._get_active_organization(
            organization_id,
            for_update=True,
        )
        membership = self._get_membership(organization_id, membership_id)
        if data.role is None:
            raise RuntimeError("Membership role was not provided")
        self._validate_role(organization, data.role)
        if (
            membership.is_active
            and membership.role == "organization_admin"
            and data.role != "organization_admin"
        ):
            self._ensure_other_active_administrator(membership)
        membership.role = data.role
        self.session.commit()
        self.session.refresh(membership)
        return membership

    def deactivate_membership(
        self,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID,
    ) -> OrganizationMembership:
        self._get_organization(organization_id, for_update=True)
        membership = self._get_membership(organization_id, membership_id)
        if not membership.is_active:
            return membership
        if membership.role == "organization_admin":
            self._ensure_other_active_administrator(membership)
        membership.is_active = False
        self.session.commit()
        self.session.refresh(membership)
        return membership

    def _get_organization(
        self,
        organization_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Organization:
        organization = self.organization_repository.get_by_id(
            organization_id,
            for_update=for_update,
        )
        if organization is None:
            raise MembershipOrganizationNotFoundError
        return organization

    def _get_active_organization(
        self,
        organization_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Organization:
        organization = self._get_organization(
            organization_id,
            for_update=for_update,
        )
        if not organization.is_active:
            raise MembershipOrganizationInactiveError
        return organization

    def _get_membership(
        self,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID,
    ) -> OrganizationMembership:
        membership = self.repository.get_membership(organization_id, membership_id)
        if membership is None:
            raise MembershipNotFoundError
        return membership

    def _validate_role(self, organization: Organization, role: MembershipRole) -> None:
        if role == "buyer" and organization.organization_type not in {"buyer", "both"}:
            raise MembershipRoleIncompatibleError
        if role in SUPPLIER_ROLES and organization.organization_type not in {
            "supplier",
            "both",
        }:
            raise MembershipRoleIncompatibleError

    def _ensure_other_active_administrator(
        self,
        membership: OrganizationMembership,
    ) -> None:
        if not self.repository.has_other_active_administrator(
            membership.organization_id,
            membership.id,
        ):
            raise MembershipLastAdministratorError

    def _commit(self, conflict_error: type[Exception]) -> None:
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise conflict_error from error
