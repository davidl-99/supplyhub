import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

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

    def list_all(self) -> list[Organization]:
        statement = select(Organization).order_by(
            Organization.created_at.desc(),
        )

        return list(self.session.scalars(statement).all())

    def add(self, organization: Organization) -> None:
        self.session.add(organization)
