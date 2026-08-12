from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class Permission(StrEnum):
    ORGANIZATION_READ = "organization:read"
    ORGANIZATION_UPDATE = "organization:update"
    ORGANIZATION_DEACTIVATE = "organization:deactivate"

    MEMBERSHIP_READ = "membership:read"
    MEMBERSHIP_CREATE = "membership:create"
    MEMBERSHIP_UPDATE = "membership:update"
    MEMBERSHIP_DEACTIVATE = "membership:deactivate"

    PRODUCT_READ = "product:read"
    PRODUCT_CREATE = "product:create"
    PRODUCT_UPDATE = "product:update"
    PRODUCT_DEACTIVATE = "product:deactivate"

    WAREHOUSE_READ = "warehouse:read"
    WAREHOUSE_CREATE = "warehouse:create"
    WAREHOUSE_UPDATE = "warehouse:update"
    WAREHOUSE_DEACTIVATE = "warehouse:deactivate"

    INVENTORY_READ = "inventory:read"
    INVENTORY_ADJUST = "inventory:adjust"

    RESERVATION_READ = "reservation:read"
    RESERVATION_CREATE = "reservation:create"
    RESERVATION_RELEASE = "reservation:release"
    RESERVATION_CONSUME = "reservation:consume"

    ORDER_READ = "order:read"
    ORDER_CREATE = "order:create"
    ORDER_PLACE = "order:place"
    ORDER_CANCEL = "order:cancel"
    ORDER_FULFILL = "order:fulfill"


ALL_PERMISSIONS = frozenset(Permission)

_ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "organization_admin": ALL_PERMISSIONS,
    "catalog_manager": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PRODUCT_READ,
            Permission.PRODUCT_CREATE,
            Permission.PRODUCT_UPDATE,
            Permission.PRODUCT_DEACTIVATE,
        }
    ),
    "warehouse_operator": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PRODUCT_READ,
            Permission.WAREHOUSE_READ,
            Permission.INVENTORY_READ,
            Permission.INVENTORY_ADJUST,
            Permission.RESERVATION_READ,
            Permission.RESERVATION_CREATE,
            Permission.RESERVATION_RELEASE,
            Permission.RESERVATION_CONSUME,
            Permission.ORDER_READ,
            Permission.ORDER_FULFILL,
        }
    ),
    "buyer": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.ORDER_READ,
            Permission.ORDER_CREATE,
            Permission.ORDER_PLACE,
            Permission.ORDER_CANCEL,
        }
    ),
    "viewer": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PRODUCT_READ,
            Permission.WAREHOUSE_READ,
            Permission.INVENTORY_READ,
            Permission.RESERVATION_READ,
            Permission.ORDER_READ,
        }
    ),
}

ROLE_PERMISSIONS: Mapping[str, frozenset[Permission]] = MappingProxyType(
    _ROLE_PERMISSIONS
)


def permissions_for_role(role: str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for_role(role)
