from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.auth.errors import AuthenticationError
from app.platform.auth.services import (
    AuthenticatedContext,
    access_token_service,
    authentication_service,
)


bearer_scheme = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


async def get_authenticated_context(
    session: DatabaseSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AuthenticatedContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = access_token_service.decode(credentials.credentials)
        return await authentication_service.validate_access_context(session, claims)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


AuthenticatedIdentity = Annotated[
    AuthenticatedContext,
    Depends(get_authenticated_context),
]
