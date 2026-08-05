class InventoryProductNotFoundError(Exception):
    pass


class InventoryProductInactiveError(Exception):
    pass


class InventoryWarehouseNotFoundError(Exception):
    pass


class InventoryWarehouseInactiveError(Exception):
    pass


class InventoryOrganizationMismatchError(Exception):
    pass


class InsufficientInventoryError(Exception):
    pass


class InventoryLevelNotFoundError(Exception):
    pass


class InsufficientAvailableInventoryError(Exception):
    pass


class InventoryReservationNotFoundError(Exception):
    pass


class InventoryReservationNotActiveError(Exception):
    pass
