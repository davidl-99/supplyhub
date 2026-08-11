from sqlalchemy.orm import Session

from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    verify_password,
)
from app.models.identity import User
from app.modules.auth.exceptions import (
    InactiveAuthenticatedUserError,
    InvalidCredentialsError,
)
from app.modules.identity.repository import IdentityRepository


class AuthenticationService:
    def __init__(self, session: Session) -> None:
        self.repository = IdentityRepository(session)

    def authenticate(self, email: str, password: str) -> User:
        normalized_email = email.strip().lower()
        user = self.repository.get_user_by_email(normalized_email)
        encoded_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        password_is_valid = verify_password(password, encoded_hash)

        if user is None or not password_is_valid:
            raise InvalidCredentialsError
        if not user.is_active:
            raise InactiveAuthenticatedUserError
        return user

    def create_token(self, user: User) -> str:
        return create_access_token(user.id)
