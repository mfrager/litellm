#!/usr/bin/env python3
"""
Test script to verify the accounts module integration with router handlers.
"""

import os
import sys
import pytest
import pytest_asyncio
from decimal import Decimal
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv('../../../.env')
sys.path.append('../..')

# Import the modules
from models.router_model import User, Workspace, Token, Base
from models.ledger_model import SQLAccount, Base as LedgerBase
from ledger.ledger_api import Ledger
from ledger.sql_ledger import SQLLedgerAPI
from router.accounts import LedgerManager

# Constants
DECIMALS = 10
SCALE = Decimal(10) ** DECIMALS

@pytest_asyncio.fixture(scope="function")
async def database_setup():
    """Set up MySQL database and return session with ledger API."""
    # Get MySQL database URL from environment
    database_url = os.environ['DATABASE_ASYNC_TEST']
    
    # Convert async URL to sync URL for SQLAlchemy session
    sync_url = database_url.replace('mysql+aiomysql://', 'mysql+pymysql://')
    
    # Create MySQL database engine
    engine = create_engine(sync_url, echo=False)
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Create Ledger configuration
    ledger_config = Ledger(
        id=1,
        accounts=[],
        has_journal=True,
        has_transactions=True,
        config={"currency": "USD", "decimals": DECIMALS}
    )
    
    # Create SQL Ledger API
    sql_ledger_api = SQLLedgerAPI(ledger_config, database_url)
    
    yield session, sql_ledger_api
    
    # Cleanup
    session.close()
    await sql_ledger_api.close()

@pytest_asyncio.fixture
async def sql_ledger_api(database_setup):
    """Get SQL ledger API from setup."""
    _, sql_ledger_api = database_setup
    return sql_ledger_api

@pytest.mark.asyncio
async def test_ledger_manager(sql_ledger_api):
    """Test the LedgerManager functionality."""
    print("\n🧪 Testing Ledger Manager...")
    
    # Get session from sql_ledger_api
    await sql_ledger_api.begin_transaction()
    try:
        session = sql_ledger_api.get_session()
        
        # Create ledger manager with session
        ledger_manager = LedgerManager(session)
    
        # Verify all required accounts are available
        required_accounts = [
            "internal_cc_processor",
            "internal_cash",
            "internal_revenue", 
            "internal_cost",
            "internal_payable"
        ]
        
        for account_code in required_accounts:
            account_id = await ledger_manager.get_account_id(account_code)
            assert account_id is not None, f"Account {account_code} should have an ID"
            print(f"   ✅ {account_code}: {account_id}")
        
        # Test transaction builder creation (router accounts)
        tx_builder = await ledger_manager.create_transaction_builder([
            "ar_processor", "unearned_revenue", "revenue_product_a"
        ])
        assert tx_builder is not None, "Should create transaction builder"
        assert len(tx_builder.account_ids) == 3, "Should have 3 account IDs for router operations"
        
        # Test transaction builder with all accounts
        tx_builder_all = await ledger_manager.create_transaction_builder([
            "ar_processor", "unearned_revenue", "revenue_product_a", 
            "cash_bank", "service_fees_expense"
        ])
        assert tx_builder_all is not None, "Should create transaction builder with all accounts"
        assert len(tx_builder_all.account_ids) == 5, "Should have 5 account IDs when all included"
        
        # Test transaction builder with custom subset
        tx_builder_custom = await ledger_manager.create_transaction_builder([
            "ar_processor", "unearned_revenue"
        ])
        assert tx_builder_custom is not None, "Should create transaction builder with custom subset"
        assert len(tx_builder_custom.account_ids) == 2, "Should have 2 account IDs for custom subset"
        
        # Test minimum balance
        min_balance = ledger_manager.get_minimum_balance()
        assert min_balance == Decimal("10.00"), f"Minimum balance should be $10.00, got ${min_balance}"
        
        print(f"\n✅ Ledger Manager test completed successfully!")
        print(f"   Total accounts tested: {len(required_accounts)}")
        print(f"   Router transaction builder accounts: {len(tx_builder.account_ids)}")
        print(f"   Full transaction builder accounts: {len(tx_builder_all.account_ids)}")
        print(f"   Custom transaction builder accounts: {len(tx_builder_custom.account_ids)}")
        print(f"   Minimum balance: ${min_balance}")
        print(f"   Decimal precision: {DECIMALS} places")
        
    finally:
        await sql_ledger_api.end_transaction()

@pytest.mark.asyncio
async def test_user_balance_operations(sql_ledger_api):
    """Test user balance account creation and checking."""
    print("\n🧪 Testing User Balance Operations...")
    
    # Get session from sql_ledger_api
    await sql_ledger_api.begin_transaction()
    try:
        session = sql_ledger_api.get_session()
        
        # Create ledger manager with session
        ledger_manager = LedgerManager(session)
    
        # Create a test user and workspace
        test_user = User(
            id="test_user_123",
            email="test@example.com",
            first_name="Test",
            last_name="User"
        )
        
        test_workspace = Workspace(
            id="test_workspace_456",
            owner_id="test_user_123"
        )
        
        # Test creating user balance account
        balance_account = await ledger_manager.create_user_balance_account(test_user, test_workspace)
        assert balance_account is not None, "Should create balance account"
        assert balance_account.account_code == f"user_{test_user.id}_balance", "Account code should match user ID"
        assert balance_account.account_type.value == "liability", "Should be liability account"
        assert balance_account.side.value == "credit", "Should be credit side"
        
        print(f"   ✅ Created balance account: {balance_account.account_code}")
        
        # Test getting user balance account
        retrieved_account = await ledger_manager.get_user_balance_account(test_user, test_workspace)
        assert retrieved_account is not None, "Should retrieve balance account"
        assert retrieved_account.id == balance_account.id, "Should be the same account"
        
        print(f"   ✅ Retrieved balance account: {retrieved_account.account_code}")
        
        # Test balance checking (should fail due to zero balance)
        has_sufficient, current_balance, error_msg = await ledger_manager.check_user_balance(test_user, test_workspace)
        assert not has_sufficient, "Should not have sufficient balance initially"
        assert current_balance == Decimal("0"), "Initial balance should be zero"
        assert error_msg is not None, "Should have error message"
        
        print(f"   ✅ Balance check: ${current_balance:.10f} (insufficient)")
        print(f"   Error: {error_msg}")
        
        print(f"\n✅ User Balance Operations test completed successfully!")
        
    finally:
        await sql_ledger_api.end_transaction()

@pytest.mark.asyncio
async def test_transaction_builder_integration(sql_ledger_api):
    """Test integration with LedgerTransactionBuilder."""
    print("\n🧪 Testing Transaction Builder Integration...")
    
    # Get session from sql_ledger_api
    await sql_ledger_api.begin_transaction()
    try:
        session = sql_ledger_api.get_session()
        
        # Create ledger manager with session
        ledger_manager = LedgerManager(session)
        
        # Create transaction builder
        tx_builder = await ledger_manager.create_transaction_builder([
            "ar_processor", "unearned_revenue", "revenue_product_a", 
            "cash_bank", "service_fees_expense"
        ])
        assert tx_builder is not None, "Should create transaction builder"
        
        # Test that we can access account IDs
        account_ids = tx_builder.account_ids
        assert len(account_ids) == 5, "Should have 5 account IDs"
        
        print(f"   ✅ Transaction builder created with {len(account_ids)} accounts")
        
        # Test account ID mapping
        expected_keys = ["cash_bank", "ar_processor", "unearned_revenue", "revenue_product_a", "service_fees_expense"]
        for key in expected_keys:
            assert key in account_ids, f"Should have {key} in account IDs"
            print(f"   ✅ {key}: {account_ids[key]}")
        
        print(f"\n✅ Transaction Builder Integration test completed successfully!")
        
    finally:
        await sql_ledger_api.end_transaction()

# Pytest will automatically discover and run the test functions
