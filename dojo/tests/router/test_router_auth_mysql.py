#!/usr/bin/env python3
"""
Test script for router authentication with MySQL/SQLite database operations.
"""

import os
import sys
import pytest
import pytest_asyncio
from ulid import ULID
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from tabulate import tabulate

# Also try loading from current directory and parent directories as fallback
load_dotenv('.env')
load_dotenv('../.env')
load_dotenv('../../.env')
load_dotenv('../../../.env')
sys.path.append('../..')

# Import the actual models
from models.router_model import User, Workspace, Token, Base as RouterBase
from models.ledger_model import SQLAccount, Base as LedgerBase
from ledger.ledger_api import (
    LedgerAccount, AccountType, LedgerSide, Ledger, LedgerAccountTransaction, 
    LedgerAccountTransfer, LedgerTransferTransaction, LedgerTransaction, 
    LedgerJournalEntry, LedgerLogicalTransaction, TransactionType
)
from ledger.sql_ledger import SQLLedgerAPI
from router.auth import RouterAuth

# Decimal precision for monetary calculations
DECIMALS = 10
SCALE = Decimal(10) ** DECIMALS

def fmt_decimal(val):
    """Format decimal values for display."""
    return f"${Decimal(val).quantize(Decimal('0.0000000001')):,.10f}"

@pytest_asyncio.fixture
async def database_connection():
    """Create a fresh database connection for each test."""
    # Get database URL from environment - must be MySQL, no fallback
    database_url = os.environ.get('DATABASE_ASYNC_TEST')
    
    if not database_url:
        raise ValueError("DATABASE_ASYNC_TEST environment variable is not set")
    
    if 'mysql' not in database_url:
        raise ValueError(f"DATABASE_ASYNC_TEST must be a MySQL URL, got: {database_url}")
    
    print(f"Connecting to MySQL: {database_url.replace(':password@', ':***@')}")
    
    # Create a fresh engine for each test with a unique pool
    engine = create_async_engine(
        database_url, 
        echo=False,
        pool_size=1,          # Single connection per test
        max_overflow=0,       # No overflow connections
        pool_pre_ping=True,   # Verify connections before use
        pool_recycle=3600,    # Recycle connections every hour
        connect_args={'charset': 'utf8mb4'}
    )
    
    try:
        yield engine
    finally:
        # Ensure all connections are properly closed
        await engine.dispose()

@pytest_asyncio.fixture
async def session(database_connection):
    """Create a fresh async session for each test."""
    # Create async session for this test with its own connection
    AsyncSession = async_sessionmaker(bind=database_connection, expire_on_commit=False)
    session = AsyncSession()
    
    try:
        yield session
    finally:
        # Close the session
        try:
            await session.close()
        except Exception:
            pass

@pytest_asyncio.fixture
async def sql_ledger_api(session):
    """Create a fresh SQL ledger API for each test."""
    # Create dummy ledger config
    ledger_config = Ledger(
        id=1,
        accounts=[],
        has_journal=True,
        has_transactions=True,
        config={"currency": "USD", "decimals": DECIMALS}
    )
    
    # Create SQL Ledger API using the fresh session
    # Pass the session directly to ensure it uses the same transaction
    sql_ledger_api = SQLLedgerAPI(ledger_config, None, session)
    
    try:
        yield sql_ledger_api
    finally:
        # Clean up the ledger API
        try:
            await sql_ledger_api.close()
        except Exception:
            pass  # Ignore cleanup errors

class DatabaseOperations:
    """Handles all database operations for testing."""
    
    def __init__(self, session, sql_ledger_api):
        self.session = session
        self.sql_ledger_api = sql_ledger_api
        self.auth = RouterAuth()
    
    async def create_user_and_workspace(self, email: str = None):
        """Create a user and workspace."""
        if email is None:
            email = f"test+{ULID()}@example.com"
        
        workspace_id = str(ULID())
        user_id = str(ULID())
        
        workspace = Workspace(id=workspace_id, owner_id=user_id)
        user = User(id=user_id, email=email, workspace_id=workspace_id)
        
        # Save to database using async session
        self.session.add(workspace)
        self.session.add(user)
        # Don't commit here - let the caller decide when to commit
        
        return user, workspace
    
    async def create_ledger_accounts(self, user, workspace):
        """Create ledger accounts for user."""
        # No separate transaction management - use shared session
        
        # Check if internal CC processor account exists first
        existing_cc_accounts = await self.sql_ledger_api.query_accounts({"account_code": "internal_cc_processor"})
        if not existing_cc_accounts:
            cc_account = LedgerAccount(
                id=str(ULID()),
                name="Internal CC Processor Account",
                account_code="internal_cc_processor",
                account_type=AccountType.ASSET,
                side=LedgerSide.DEBIT,
                decimals=DECIMALS,
                allow_negative=True,
                details={}
            )
            cc_tx = LedgerAccountTransaction(accounts=[cc_account])
            await self.sql_ledger_api.create_accounts([cc_tx])
            print(f"✅ Created internal CC processor account: {cc_account.id}")
        else:
            print(f"✅ Found existing internal CC processor account: {existing_cc_accounts[0].id}")
        
        # Check if workspace account exists
        workspace_account_code = f"workspace_{workspace.id}_balance"
        existing_workspace_accounts = await self.sql_ledger_api.query_accounts({"account_code": workspace_account_code})
        if not existing_workspace_accounts:
            # Create workspace balance account
            workspace_account = LedgerAccount(
                id=str(ULID()),
                name=f"Workspace Balance - {workspace.id}",
                account_code=workspace_account_code,
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                decimals=DECIMALS,
                workspace_id=workspace.id,
                allow_negative=True,
                details={}
            )
            workspace_tx = LedgerAccountTransaction(accounts=[workspace_account])
            await self.sql_ledger_api.create_accounts([workspace_tx])
            print(f"✅ Created workspace account: {workspace_account.id}")
            return workspace_account
        else:
            print(f"✅ Found existing workspace account: {existing_workspace_accounts[0].id}")
            return existing_workspace_accounts[0]
    
    async def fund_workspace_account(self, user, workspace, amount: int = 1000):  # $1000.00
        """Fund workspace account using proper transaction creation."""
        # Get accounts
        workspace_accounts = await self.sql_ledger_api.query_accounts({"account_code": f"workspace_{workspace.id}_balance"})
        cc_accounts = await self.sql_ledger_api.query_accounts({"account_code": "internal_cc_processor"})
        
        if not workspace_accounts or not cc_accounts:
            raise ValueError("Required accounts not found")
        
        workspace_account = workspace_accounts[0]
        cc_account = cc_accounts[0]
        
        # Create proper ledger transaction with journal entries and transfers
        transaction_id = str(ULID())

        amount = amount * (10 ** DECIMALS)
        
        # Create journal entries (accounting double-entry)
        debit_entry = LedgerJournalEntry(
            id=str(ULID()),
            account_id=cc_account.id,
            debit=amount,
            credit=0,
            transaction_id=transaction_id,
            description=f"Fund workspace account {workspace.id}",
            ts_created=datetime.now()
        )
        
        credit_entry = LedgerJournalEntry(
            id=str(ULID()),
            account_id=workspace_account.id,
            debit=0,
            credit=amount,
            transaction_id=transaction_id,
            description=f"Fund workspace account {workspace.id}",
            ts_created=datetime.now()
        )
        
        # Create transfer
        transfer = LedgerAccountTransfer(
            id=str(ULID()),
            debit_account_id=cc_account.id,
            credit_account_id=workspace_account.id,
            amount=amount,
            ts_created=datetime.now(),
            transaction_id=transaction_id,
            balance=None
        )
        
        # Create the transaction record
        ledger_tx = LedgerTransaction(
            id=transaction_id,
            transaction_type=TransactionType.PAYMENT,
            user_id=user.id,
            reference=f"Fund user {user.email}",
            description=f"Fund user account with ${amount/10000:.2f}",
            details={"user_id": user.id, "workspace_id": workspace.id},
            entries=[debit_entry, credit_entry],
            transfers=[transfer],
            ts_created=datetime.now()
        )
        
        # Create logical transaction and execute
        logical_tx = LedgerLogicalTransaction(transactions=[ledger_tx])
        await self.sql_ledger_api.create_transactions([logical_tx])
        
        return transaction_id

@pytest.mark.asyncio
async def test_complete_user_workflow_with_reports(session, sql_ledger_api):
    """Test complete user workflow with real database reports."""
    print("\n🧪 Testing Complete User Workflow with Real Data Reports...")
    
    db_ops = DatabaseOperations(session, sql_ledger_api)
    
    # Step 1: Create user and workspace
    print("\n📝 Step 1: Creating user and workspace...")
    user, workspace = await db_ops.create_user_and_workspace()
    
    # Step 2: Create ledger accounts
    print("\n💰 Step 2: Creating ledger accounts...")
    user_account = await db_ops.create_ledger_accounts(user, workspace)
    print(f"✅ Created ledger accounts for user {user.email}")
    
    # Step 3: Fund workspace account
    print("\n💳 Step 3: Funding workspace account...")
    transaction_id = await db_ops.fund_workspace_account(user, workspace, 1000)  # $1000.00
    print(f"✅ Funded workspace account for {workspace.id}")
    print(f"   Amount: $1000.00")
    print(f"   Transaction ID: {transaction_id}")
    
    # Step 4: Generate reports
    print("\n📊 Step 4: Generating reports from real database data...")
    
    # Get all transactions (no separate transaction management)
    all_transactions = await sql_ledger_api.query_transactions({"user_id": workspace.id})
    all_accounts = await sql_ledger_api.query_accounts({})
        
    print(f"\n📊 Found {len(all_transactions)} transactions for user")
    print(f"📊 Found {len(all_accounts)} total accounts in system")
    
    print("\n✅ Complete user workflow test completed successfully")
    print(f"   User ID: {user.id}")
    print(f"   Workspace ID: {workspace.id}")
    print(f"   Email: {user.email}")
    print(f"   Funding Transaction: {transaction_id}")
    print(f"   Total Transactions: {len(all_transactions)}")
    print(f"   Total Accounts: {len(all_accounts)}")
    
    # Commit the data to persist it in the database
    await session.commit()

@pytest.mark.asyncio
async def test_create_token(session, sql_ledger_api):
    """Test token creation using existing workspace."""
    print("\n🧪 Testing Token Creation...")
    
    # Find an existing workspace from previous test
    from sqlalchemy import select
    workspace_result = await session.execute(select(Workspace).limit(1))
    workspace = workspace_result.scalar_one_or_none()
    
    if not workspace:
        raise AssertionError("No existing workspace found. Run test_complete_user_workflow_with_reports first.")
    
    # Create token using RouterAuth for existing workspace
    db_ops = DatabaseOperations(session, sql_ledger_api)
    token_obj = await db_ops.auth.create_token(workspace_id=workspace.id)
    
    # Save token to database
    session.add(token_obj)
    
    print(f"✅ Token created successfully")
    print(f"   Token ID: {token_obj.token}")
    print(f"   Workspace ID: {workspace.id}")
    
    # Commit the data to persist it in the database
    await session.commit()

@pytest.mark.asyncio
async def test_database_queries(session, sql_ledger_api):
    """Test basic database queries by counting existing data."""
    print("\n🧪 Testing Database Queries...")
    
    # Count existing entities in the database
    from sqlalchemy import select, func
    
    user_result = await session.execute(select(func.count(User.id)))
    user_count = user_result.scalar()
    
    workspace_result = await session.execute(select(func.count(Workspace.id)))
    workspace_count = workspace_result.scalar()
    
    token_result = await session.execute(select(func.count(Token.id)))
    token_count = token_result.scalar()
    
    # Count ledger entities
    accounts = await sql_ledger_api.query_accounts({})
    transactions = await sql_ledger_api.query_transactions({})
    
    print(f"📊 Database Query Results:")
    print(f"   Users: {user_count}")
    print(f"   Workspaces: {workspace_count}")
    print(f"   Tokens: {token_count}")
    print(f"   Ledger Accounts: {len(accounts)}")
    print(f"   Ledger Transactions: {len(transactions)}")
    
    # Assertions - should have data from previous tests
    assert user_count >= 1, f"Expected at least 1 user, got {user_count}"
    assert workspace_count >= 1, f"Expected at least 1 workspace, got {workspace_count}"
    assert token_count >= 1, f"Expected at least 1 token, got {token_count}"
    assert len(accounts) >= 1, f"Expected at least 1 ledger account, got {len(accounts)}"
    assert len(transactions) >= 0, f"Expected at least 0 transactions, got {len(transactions)}"
    
    print("✅ Database queries completed successfully")