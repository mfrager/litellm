from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Date, Enum, Index, DECIMAL, JSON, Table
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from .base import Base, ULID_BINARY
from .common import CommonBase
from .functions import generate_ulid, generate_utcnow

class Workspace(CommonBase, Base):
    __tablename__ = 'router_workspace'
    
    id = Column[bytes](ULID_BINARY, primary_key=True, default=generate_ulid)
    owner_id = Column[bytes](ULID_BINARY, nullable=False)
    is_active = Column[bool](Boolean, default=True)
    
    # Relationships
    owner = relationship("User", back_populates="owned_workspaces", foreign_keys=[owner_id], primaryjoin="Workspace.owner_id == User.id")

class User(CommonBase, Base):
    __tablename__ = 'router_user'
    
    id = Column[bytes](ULID_BINARY, primary_key=True, default=generate_ulid)
    workspace_id = Column[bytes](ULID_BINARY, nullable=True, index=True)
    email = Column[str](String(255), unique=True, nullable=False)
    keycloak_uuid = Column[str](String(36), unique=True, nullable=True)
    first_name = Column[str](String(100), nullable=True)
    last_name = Column[str](String(100), nullable=True)
    phone = Column[str](String(20), nullable=True)
    company = Column[str](String(255), nullable=True)
    is_active = Column[bool](Boolean, default=True)
    last_login = Column[datetime](DateTime, nullable=True)
    
    # Relationships
    workspace = relationship("Workspace", foreign_keys=[workspace_id], primaryjoin="User.workspace_id == Workspace.id")
    owned_workspaces = relationship("Workspace", back_populates="owner", primaryjoin="User.id == foreign(Workspace.owner_id)")

class Model(CommonBase, Base):
    __tablename__ = 'router_model'

    id = Column[bytes](ULID_BINARY, primary_key=True, default=generate_ulid)
    model_id = Column[str](String(255), nullable=False, unique=True)   # e.g. "lmstudio/lfm2.5-1.2b-instruct-mlx"
    model_group = Column[str](String(32), nullable=False)              # "local" | "remote"
    model_tag = Column[str](String(32), nullable=False)                # "code" | "large" | "small"
    default_context_length = Column[int](Integer, nullable=False, default=8192)
    is_default = Column[bool](Boolean, nullable=False, default=False)
    priority = Column[int](Integer, nullable=False, default=1)         # higher = tried first; min 1
    is_active = Column[bool](Boolean, nullable=False, default=True)
    base_url = Column[str](String(512), nullable=True)                 # optional API base URL for this model
    backend_model = Column[str](String(255), nullable=True)            # litellm_params "model:" value (e.g. openai/liquid/...)
    api_key = Column[str](String(255), nullable=True)                  # litellm_params "api_key:" value, emitted quoted in YAML (e.g. "os.environ/KEY" or "none")
    drop_params = Column[bool](Boolean, nullable=False, default=False)  # litellm_params "drop_params: true" when set

    __table_args__ = (
        Index('idx_model_group', 'model_group'),
        Index('idx_model_tag', 'model_tag'),
        Index('idx_model_group_tag', 'model_group', 'model_tag'),
        Index('idx_model_priority', 'priority'),
        Index('idx_model_is_default', 'is_default'),
    )


class Token(CommonBase, Base):
    __tablename__ = 'router_token'
    
    id = Column[bytes](ULID_BINARY, primary_key=True, default=generate_ulid)
    token = Column[str](String(64), nullable=False, unique=True)           # The actual token
    workspace_id = Column[bytes](ULID_BINARY, nullable=False)                 # ULID for workspace reference
    is_active = Column[bool](Boolean, nullable=False, default=True)         # Active flag
    last_access = Column[datetime](DateTime, nullable=True)                     # Last use of API token

    workspace = relationship("Workspace", foreign_keys=[workspace_id], primaryjoin="Token.workspace_id == Workspace.id")


class RequestLog(CommonBase, Base):
    """Tracks each LLM request outcome without storing request or response payloads."""

    __tablename__ = 'router_request_log'

    id = Column[bytes](ULID_BINARY, primary_key=True, default=generate_ulid)
    request_id = Column[bytes](ULID_BINARY, nullable=False, index=True)     # shared across log rows for one client request
    workspace_id = Column[bytes](ULID_BINARY, nullable=False, index=True)
    model = Column[str](String(255), nullable=False)                          # internal model_id (matches fallback_sequence)
    is_success = Column[bool](Boolean, nullable=False)
    fallback_sequence = Column(JSON, nullable=True)                         # ordered model ids tried/planned for fallback
    token_metadata = Column(JSON, nullable=True)                            # prompt/completion/total/cached token counts
    error_details = Column(JSON, nullable=True)                             # populated when is_success is False

    workspace = relationship(
        "Workspace",
        foreign_keys=[workspace_id],
        primaryjoin="RequestLog.workspace_id == Workspace.id",
    )

    __table_args__ = (
        Index('idx_request_log_workspace_ts', 'workspace_id', 'ts_created'),
        Index('idx_request_log_model', 'model'),
        Index('idx_request_log_is_success', 'is_success'),
    )

