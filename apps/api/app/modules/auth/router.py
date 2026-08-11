from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.exceptions import AuthenticationError
from app.modules.auth.schemas import AccessTokenRead
from app.modules.auth.service import AuthenticationService
from app.modules.identity.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["Authentication"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


@router.post("/token", response_model=AccessTokenRead)
def create_access_token(
    form_data: LoginForm,
    session: DatabaseSession,
) -> AccessTokenRead:
    service = AuthenticationService(session)
    try:
        user = service.authenticate(form_data.username, form_data.password)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    return AccessTokenRead(access_token=service.create_token(user))


@router.get("/me", response_model=UserRead)
def get_authenticated_user(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
