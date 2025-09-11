from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Date, Enum, Index, DECIMAL, JSON, Table
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from .base import Base
from .common import CommonBase
from .functions import generate_ulid, generate_utcnow

class Workspace(CommonBase, Base):
    __tablename__ = 'router_workspace'
    
    id = Column(String(26), primary_key=True, default=generate_ulid)
    owner_id = Column(String(26), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    owner = relationship("User", back_populates="owned_workspaces", foreign_keys=[owner_id], primaryjoin="Workspace.owner_id == User.id")

class User(CommonBase, Base):
    __tablename__ = 'router_user'
    
    id = Column(String(26), primary_key=True, default=generate_ulid)
    workspace_id = Column(String(26), nullable=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    keycloak_uuid = Column(String(36), unique=True, nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    company = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    workspace = relationship("Workspace", foreign_keys=[workspace_id], primaryjoin="User.workspace_id == Workspace.id")
    owned_workspaces = relationship("Workspace", back_populates="owner", primaryjoin="User.id == foreign(Workspace.owner_id)")

class Token(CommonBase, Base):
    __tablename__ = 'router_token'
    
    id = Column(String(26), primary_key=True, default=generate_ulid)
    token = Column(String(64), nullable=False, unique=True)           # The actual token
    user_id = Column(String(26), nullable=False)                      # ULID for user reference
    is_active = Column(Boolean, nullable=False, default=True)         # Active flag
    last_access = Column(DateTime, nullable=True)                     # Last use of API token

