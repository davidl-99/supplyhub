class IdentityError(Exception):
    pass


class UserNotFoundError(IdentityError):
    pass


class UserEmailAlreadyExistsError(IdentityError):
    pass


class UserInactiveError(IdentityError):
    pass


class MembershipNotFoundError(IdentityError):
    pass


class MembershipAlreadyExistsError(IdentityError):
    pass


class MembershipOrganizationNotFoundError(IdentityError):
    pass


class MembershipOrganizationInactiveError(IdentityError):
    pass


class MembershipRoleIncompatibleError(IdentityError):
    pass


class MembershipLastAdministratorError(IdentityError):
    pass
