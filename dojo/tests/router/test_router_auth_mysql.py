#!/usr/bin/env python3
"""
Simple test script for RouterAuth
"""

import os
import sys
import string
import secrets
import asyncio
from ulid import ULID
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv('../../../.env')
sys.path.append('../..')

# Import the actual models
from models.router_model import User, Workspace, Token, Base

# Database-enabled RouterAuth
class RouterAuth:
    """Simple authentication class for creating users associated with workspaces."""
    
    def __init__(self, session):
        self.session = session
    
    def create_user(self, email: str, keycloak_uuid: str = None, first_name: str = None, 
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
        
        # Save to database
        self.session.add(workspace)
        self.session.add(user)
        self.session.commit()
        
        return user, workspace
    
    def create_token(self, workspace_id: str) -> Token:
        """Create a new token instance for a workspace."""
        
        alphabet = string.ascii_letters  # A-Za-z
        token = ''.join(secrets.choice(alphabet) for _ in range(64))
        
        token_obj = Token(
            id=str(ULID()),
            workspace_id=workspace_id,
            token=token
        )
        
        # Save to database
        self.session.add(token_obj)
        self.session.commit()
        
        return token_obj

def setup_database():
    """Set up MySQL database and return session."""
    # Get MySQL database URL from environment
    database_url = os.environ['DATABASE_ASYNC_TEST']
    
    # Convert async URL to sync URL for SQLAlchemy session
    sync_url = database_url.replace('mysql+aiomysql://', 'mysql+pymysql://')
    
    # Create MySQL database engine
    engine = create_engine(sync_url, echo=False)
    
    # Drop all tables first to ensure clean schema
    Base.metadata.drop_all(engine)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    return session

def test_create_user(session):
    """Test user and workspace creation."""
    print("🧪 Testing RouterAuth.create_user()...")
    
    auth = RouterAuth(session)
    
    # Use unique email with timestamp to avoid duplicates
    import time
    unique_email = f"test+{int(time.time())}@example.com"
    
    user, workspace = auth.create_user(
        email=unique_email,
        first_name="Test",
        last_name="User"
    )
    
    # Verify user creation
    assert user.email == unique_email
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert user.workspace_id == workspace.id
    assert len(user.id) == 26  # ULID length
    
    # Verify workspace creation
    assert workspace.owner_id == user.id
    assert len(workspace.id) == 26  # ULID length
    
    # Verify data was saved to database
    db_user = session.query(User).filter_by(id=user.id).first()
    db_workspace = session.query(Workspace).filter_by(id=workspace.id).first()
    
    assert db_user is not None
    assert db_workspace is not None
    assert db_user.email == unique_email
    assert db_workspace.owner_id == user.id
    
    print("✅ User and workspace created successfully")
    print(f"   User ID: {user.id}")
    print(f"   Workspace ID: {workspace.id}")
    print(f"   Email: {user.email}")
    
    return user, workspace

def test_create_token(session):
    """Test token creation."""
    print("\n🧪 Testing RouterAuth.create_token()...")
    
    auth = RouterAuth(session)
    
    # Use unique email with timestamp to avoid duplicates
    import time
    unique_email = f"token+{int(time.time())}@example.com"
    
    user, workspace = auth.create_user(email=unique_email)
    
    token = auth.create_token(workspace_id=workspace.id)
    
    # Verify token creation
    assert token.workspace_id == workspace.id
    assert len(token.token) == 64  # Exactly 64 characters
    assert token.token.isalpha()  # Only A-Za-z characters
    assert len(token.id) == 26  # ULID length
    
    # Verify data was saved to database
    db_token = session.query(Token).filter_by(id=token.id).first()
    assert db_token is not None
    assert db_token.token == token.token
    assert db_token.workspace_id == workspace.id
    
    print("✅ Token created successfully")
    print(f"   Token ID: {token.id}")
    print(f"   Token: {token.token[:20]}...{token.token[-20:]}")  # Show first/last 20 chars
    print(f"   Workspace ID: {token.workspace_id}")
    
    return token

def test_database_queries(session):
    """Test database queries to verify data persistence."""
    print("\n🧪 Testing database queries...")
    
    # Count all records
    user_count = session.query(User).count()
    workspace_count = session.query(Workspace).count()
    token_count = session.query(Token).count()
    
    print(f"   Users in database: {user_count}")
    print(f"   Workspaces in database: {workspace_count}")
    print(f"   Tokens in database: {token_count}")
    
    # Verify we have data
    assert user_count >= 2  # At least 2 users from previous tests
    assert workspace_count >= 2  # At least 2 workspaces
    assert token_count >= 1  # At least 1 token
    
    print("✅ Database queries successful")

def main():
    """Run all tests."""
    print("🚀 RouterAuth Test Suite with MySQL Database")
    print("=" * 50)
    
    session = None
    try:
        # Set up database
        session = setup_database()
        print("📊 Database initialized (MySQL)")
        
        # Test user creation
        user, workspace = test_create_user(session)
        
        # Test token creation
        token = test_create_token(session)
        
        # Test database queries
        test_database_queries(session)
        
        print("\n🎉 All tests passed!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if session:
            session.close()
    
    return 0

if __name__ == "__main__":
    exit(main())
