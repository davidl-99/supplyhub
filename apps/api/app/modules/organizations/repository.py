from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization


class OrganizationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

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