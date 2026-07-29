import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.modules.organizations.exceptions import (
    OrganizationNotFoundError,
    OrganizationSlugAlreadyExistsError,
)
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import (
    OrganizationCreate,
    OrganizationUpdate,
)


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
        self._commit()

        self.session.refresh(organization)

        return organization

    def get_by_id(
        self,
        organization_id: uuid.UUID,
    ) -> Organization:
        organization = self.repository.get_by_id(organization_id)

        if organization is None:
            raise OrganizationNotFoundError

        return organization

    def list_all(self) -> list[Organization]:
        return self.repository.list_all()

    def update(
        self,
        organization_id: uuid.UUID,
        data: OrganizationUpdate,
    ) -> Organization:
        organization = self.get_by_id(organization_id)

        #convierte el esquema en un diccionario, pero únicamente incluye 
        # los campos enviados por el cliente.
        changes = data.model_dump(exclude_unset=True)

        new_slug = changes.get("slug")

        if new_slug is not None and new_slug != organization.slug:
            existing_organization = self.repository.get_by_slug(new_slug)

            if existing_organization is not None:
                raise OrganizationSlugAlreadyExistsError

        for field_name, value in changes.items():
            setattr(organization, field_name, value)

        self._commit()
        self.session.refresh(organization)

        return organization

    def deactivate(
        self,
        organization_id: uuid.UUID,
    ) -> Organization:
        organization = self.get_by_id(organization_id)

        if not organization.is_active:
            return organization

        organization.is_active = False

        self._commit()
        self.session.refresh(organization)

        return organization

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise OrganizationSlugAlreadyExistsError from error