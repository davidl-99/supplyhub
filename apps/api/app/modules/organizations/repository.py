import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import OrganizationMembership
from app.models.organization import Organization


class OrganizationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(
        self,
        organization_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Organization | None:
        if not for_update:
            return self.session.get(
                Organization,
                organization_id,
            )

        statement = (
            select(Organization)
            .where(Organization.id == organization_id)
            .with_for_update()
        )
        return self.session.scalar(statement)

    def get_by_slug(self, slug: str) -> Organization | None:
        statement = select(Organization).where(
            Organization.slug == slug,
        )

        return self.session.scalar(statement)

    def list_for_user(self, user_id: uuid.UUID) -> list[Organization]:
        """List the organizations the user is an active member of.

        Membership is the tenant boundary: an organization the caller has no
        active membership in must not appear, so this join replaces the former
        unscoped listing that returned every tenant's organizations.
        """
        statement = (
            select(Organization)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == Organization.id,
            )
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.is_active.is_(True),
            )
            .order_by(Organization.created_at.desc())
        )

        return list(self.session.scalars(statement).all())

    def add(self, organization: Organization) -> None:
        self.session.add(organization)
