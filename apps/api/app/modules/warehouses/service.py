import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.warehouse import Warehouse
from app.modules.organizations.repository import OrganizationRepository
from app.modules.warehouses.exceptions import (
    WarehouseCodeAlreadyExistsError,
    WarehouseNotFoundError,
    WarehouseOrganizationCannotSupplyError,
    WarehouseOrganizationInactiveError,
    WarehouseOrganizationNotFoundError,
)
from app.modules.warehouses.repository import WarehouseRepository
from app.modules.warehouses.schemas import (
    WarehouseCreate,
    WarehouseListQuery,
    WarehouseUpdate,
)


class WarehouseService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.warehouse_repository = WarehouseRepository(session)
        self.organization_repository = OrganizationRepository(session)

    def create(self, data: WarehouseCreate) -> Warehouse:
        organization = self.organization_repository.get_by_id(data.organization_id)

        if organization is None:
            raise WarehouseOrganizationNotFoundError

        if not organization.is_active:
            raise WarehouseOrganizationInactiveError

        if organization.organization_type not in {"supplier", "both"}:
            raise WarehouseOrganizationCannotSupplyError

        existing_warehouse = self.warehouse_repository.get_by_organization_and_code(
            organization_id=data.organization_id,
            code=data.code,
        )

        if existing_warehouse is not None:
            raise WarehouseCodeAlreadyExistsError

        warehouse = Warehouse(
            organization_id=data.organization_id,
            code=data.code,
            name=data.name,
            address=data.address,
        )
        self.warehouse_repository.add(warehouse)
        self._commit()
        self.session.refresh(warehouse)
        return warehouse

    def get_by_id(self, warehouse_id: uuid.UUID) -> Warehouse:
        warehouse = self.warehouse_repository.get_by_id(warehouse_id)

        if warehouse is None:
            raise WarehouseNotFoundError

        return warehouse

    def list_all(
        self,
        filters: WarehouseListQuery,
    ) -> tuple[list[Warehouse], int]:
        return self.warehouse_repository.list_all(
            organization_id=filters.organization_id,
            search=filters.search,
            is_active=filters.is_active,
            limit=filters.limit,
            offset=filters.offset,
        )

    def update(
        self,
        warehouse_id: uuid.UUID,
        data: WarehouseUpdate,
    ) -> Warehouse:
        warehouse = self.get_by_id(warehouse_id)
        changes = data.model_dump(exclude_unset=True)
        new_code = changes.get("code")

        if new_code is not None and new_code != warehouse.code:
            existing_warehouse = self.warehouse_repository.get_by_organization_and_code(
                organization_id=warehouse.organization_id,
                code=new_code,
            )
            if existing_warehouse is not None:
                raise WarehouseCodeAlreadyExistsError

        for field_name, value in changes.items():
            setattr(warehouse, field_name, value)

        self._commit()
        self.session.refresh(warehouse)
        return warehouse

    def deactivate(self, warehouse_id: uuid.UUID) -> Warehouse:
        warehouse = self.get_by_id(warehouse_id)

        if not warehouse.is_active:
            return warehouse

        warehouse.is_active = False
        self._commit()
        self.session.refresh(warehouse)
        return warehouse

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise WarehouseCodeAlreadyExistsError from error
