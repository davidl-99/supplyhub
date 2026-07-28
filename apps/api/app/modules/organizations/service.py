from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.modules.organizations.exceptions import (
    OrganizationSlugAlreadyExistsError,
)
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationCreate


class OrganizationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OrganizationRepository(session)

    def create(self, data: OrganizationCreate) -> Organization:
        existing_organization = self.repository.get_by_slug(data.slug)

        if existing_organization is not None:
            raise OrganizationSlugAlreadyExistsError

        organization = Organization(
            name=data.name,
            slug=data.slug,
        )

        self.repository.add(organization)

        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise OrganizationSlugAlreadyExistsError from error

        self.session.refresh(organization)

        return organization

    def list_all(self) -> list[Organization]:
        return self.repository.list_all()