class ProductNotFoundError(Exception):
    pass


class ProductSkuAlreadyExistsError(Exception):
    pass


class ProductOrganizationNotFoundError(Exception):
    pass


class ProductOrganizationInactiveError(Exception):
    pass


class ProductOrganizationCannotSupplyError(Exception):
    pass
