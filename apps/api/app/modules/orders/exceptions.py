class OrderError(Exception):
    pass


class OrderNotFoundError(OrderError):
    pass


class OrderOrganizationNotFoundError(OrderError):
    pass


class OrderOrganizationInactiveError(OrderError):
    pass


class OrderBuyerCannotBuyError(OrderError):
    pass


class OrderSupplierCannotSupplyError(OrderError):
    pass


class OrderProductNotFoundError(OrderError):
    pass


class OrderProductUnavailableError(OrderError):
    pass


class OrderWarehouseNotFoundError(OrderError):
    pass


class OrderWarehouseUnavailableError(OrderError):
    pass


class OrderSupplierMismatchError(OrderError):
    pass


class OrderCurrencyMismatchError(OrderError):
    pass


class OrderNotDraftError(OrderError):
    pass


class OrderInsufficientInventoryError(OrderError):
    pass
