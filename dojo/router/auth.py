import string
import secrets
from ulid import ULID
from models.router_model import Token, User, Workspace

class RouterAuth:
    """Simple authentication class for creating users associated with workspaces."""
    
    async def create_user(self, email: str, keycloak_uuid: str = None, first_name: str = None, 
                   last_name: str = None, phone: str = None, company: str = None, 
                   is_active: bool = True, last_login = None) -> tuple[User, Workspace]:
        """Create a new user instance with an associated workspace."""
        user_id = str(ULID())
        workspace_id = str(ULID())
        
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
    
    async def create_token(self, workspace_id: str) -> Token:
        """Create a new token instance for a workspace."""
        alphabet = string.ascii_letters  # A-Za-z
        token = ''.join(secrets.choice(alphabet) for _ in range(64))
        return Token(
            id=str(ULID()),
            workspace_id=workspace_id,
            token=token
        )
