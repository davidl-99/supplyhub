from typing import Literal

MembershipRole = Literal[
    "organization_admin",
    "catalog_manager",
    "warehouse_operator",
    "buyer",
    "viewer",
]

MEMBERSHIP_ROLES: tuple[MembershipRole, ...] = (
    "organization_admin",
    "catalog_manager",
    "warehouse_operator",
    "buyer",
    "viewer",
)

SUPPLIER_ROLES: frozenset[MembershipRole] = frozenset(
    {"catalog_manager", "warehouse_operator"}
)
