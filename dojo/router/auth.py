import string
import secrets
from datetime import datetime
from typing import Optional, Tuple, Union

from ulid import ULID

from dojo.models.functions import generate_ulid
from dojo.models.router_model import Token, User, Workspace

class RouterAuth:
    """Simple authentication class for creating users associated with workspaces."""

    async def create_user(
        self,
        email: str,
        keycloak_uuid: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone: Optional[str] = None,
        company: Optional[str] = None,
        is_active: bool = True,
        last_login: Optional[datetime] = None,
    ) -> Tuple[User, Workspace]:
        """Create a new user instance with an associated workspace."""
        user_id = generate_ulid()
        workspace_id = generate_ulid()

        workspace = Workspace(
            id=workspace_id,  # pyright: ignore[reportCallIssue]
            owner_id=user_id,  # pyright: ignore[reportCallIssue]
        )

        user = User(
            id=user_id,  # pyright: ignore[reportCallIssue]
            workspace_id=workspace_id,  # pyright: ignore[reportCallIssue]
            email=email,  # pyright: ignore[reportCallIssue]
            keycloak_uuid=keycloak_uuid,  # pyright: ignore[reportCallIssue]
            first_name=first_name,  # pyright: ignore[reportCallIssue]
            last_name=last_name,  # pyright: ignore[reportCallIssue]
            phone=phone,  # pyright: ignore[reportCallIssue]
            company=company,  # pyright: ignore[reportCallIssue]
            is_active=is_active,  # pyright: ignore[reportCallIssue]
            last_login=last_login,  # pyright: ignore[reportCallIssue]
        )
        
        return user, workspace
    
    async def create_token(self, workspace_id: Union[str, bytes]) -> Token:
        """Create a new token instance for a workspace. workspace_id can be bytes (ULID) or str (ULID string)."""
        alphabet = string.ascii_letters  # A-Za-z
        token = "".join(secrets.choice(alphabet) for _ in range(64))
        ws_id: bytes = ULID.from_str(workspace_id).bytes if isinstance(workspace_id, str) else workspace_id
        return Token(
            id=generate_ulid(),  # pyright: ignore[reportCallIssue]
            workspace_id=ws_id,  # pyright: ignore[reportCallIssue]
            token=token,  # pyright: ignore[reportCallIssue]
        )
