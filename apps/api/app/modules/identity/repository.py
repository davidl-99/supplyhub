import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.identity import OrganizationMembership, User


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_user(self, user: User) -> None:
        self.session.add(user)

    def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_user_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def add_membership(self, membership: OrganizationMembership) -> None:
        self.session.add(membership)

    def get_membership(
        self,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID,
    ) -> OrganizationMembership | None:
        return self.session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.id == membership_id,
                OrganizationMembership.organization_id == organization_id,
            )
        )

    def get_membership_by_user(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> OrganizationMembership | None:
        return self.session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
        )

    def has_other_active_administrator(
        self,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID,
    ) -> bool:
        statement = (
            select(OrganizationMembership.id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.id != membership_id,
                OrganizationMembership.role == "organization_admin",
                OrganizationMembership.is_active.is_(True),
            )
            .limit(1)
        )
        return self.session.scalar(statement) is not None

    def list_memberships(
        self,
        organization_id: uuid.UUID,
        role: str | None = None,
        is_active: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[OrganizationMembership], int]:
        conditions = [OrganizationMembership.organization_id == organization_id]
        if role is not None:
            conditions.append(OrganizationMembership.role == role)
        if is_active is not None:
            conditions.append(OrganizationMembership.is_active == is_active)

        total = (
            self.session.scalar(
                select(func.count())
                .select_from(OrganizationMembership)
                .where(*conditions)
            )
            or 0
        )
        statement = (
            select(OrganizationMembership)
            .where(*conditions)
            .order_by(
                OrganizationMembership.created_at.desc(),
                OrganizationMembership.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement).all()), total
