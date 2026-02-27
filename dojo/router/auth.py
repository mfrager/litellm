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
            id=workspace_id,
            owner_id=user_id
        )
        
        user = User(
            id=user_id,
            workspace_id=workspace_id,
            email=email,
            keycloak_uuid=keycloak_uuid,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            company=company,
            is_active=is_active,
            last_login=last_login
        )
        
        return user, workspace
    
    async def create_token(self, workspace_id: Union[str, bytes]) -> Token:
        """Create a new token instance for a workspace. workspace_id can be bytes (ULID) or str (ULID string)."""
        alphabet = string.ascii_letters  # A-Za-z
        token = "".join(secrets.choice(alphabet) for _ in range(64))
        ws_id: bytes = ULID.from_str(workspace_id).bytes if isinstance(workspace_id, str) else workspace_id
        return Token(
            id=generate_ulid(),
            workspace_id=ws_id,
            token=token,
        )
