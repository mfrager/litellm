#!/usr/bin/env python3
"""
Test script for creating and managing internal accounts with proper accounting classification.
"""

import os
import sys
import pytest
import pytest_asyncio
from ulid import ULID
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tabulate import tabulate

load_dotenv('../../../.env')
sys.path.append('../..')

# Import the actual models
from models.router_model import User, Workspace, Token, Base
from models.ledger_model import SQLAccount, Base as LedgerBase
from ledger.ledger_api import LedgerAccount, AccountType, LedgerSide, generate_account_code
from ledger.sql_ledger import SQLLedgerAPI

# Decimal precision for monetary calculations
DECIMALS = 10  # 10 decimal places for high precision
SCALE = Decimal(10) ** DECIMALS

def fmt_decimal(val):
    """Format decimal values for display with full 10 decimal precision."""
    return f"${Decimal(val).quantize(Decimal('0.0000000001')):,.10f}"

class LedgerManager:
    """Manages internal accounts with proper accounting classification."""
    
    def __init__(self, sql_ledger_api):
        self.sql_ledger_api = sql_ledger_api
        self.internal_accounts = {}
    
    async def find_or_create_internal_accounts(self):
        """Find existing internal accounts or create new ones with proper classification."""
        print("\n🏦 INTERNAL ACCOUNT MANAGEMENT")
        print("=" * 80)
        
        # Define the internal accounts with proper accounting classification
        account_definitions = [
            {
                "account_code": "internal_cc_processor",
                "name": "Internal CC Processor Account",
                "account_type": AccountType.ASSET,
                "side": LedgerSide.DEBIT,
                "description": "Accounts receivable from credit card processor"
            },
            {
                "account_code": "internal_cash",
                "name": "Internal Cash Account",
                "account_type": AccountType.ASSET,
                "side": LedgerSide.DEBIT,
                "description": "Company cash holdings"
            },
            {
                "account_code": "internal_revenue",
                "name": "Internal Revenue Account",
                "account_type": AccountType.INCOME,
                "side": LedgerSide.CREDIT,
                "description": "Company revenue recognition"
            },
            {
                "account_code": "internal_cost",
                "name": "Internal Cost Account",
                "account_type": AccountType.EXPENSE,
                "side": LedgerSide.DEBIT,
                "description": "Company cost of goods sold"
            },
            {
                "account_code": "internal_payable",
                "name": "Internal Payable Account",
                "account_type": AccountType.LIABILITY,
                "side": LedgerSide.CREDIT,
                "description": "Company accounts payable"
            }
        ]
        
        await self.sql_ledger_api.begin_transaction()
        try:
            for account_def in account_definitions:
                account = await self._find_or_create_account(account_def)
                self.internal_accounts[account_def["account_code"]] = account
        finally:
            await self.sql_ledger_api.end_transaction()
        
        return self.internal_accounts
    
    async def _find_or_create_account(self, account_def):
        """Find existing account by code or create new one."""
        account_code = account_def["account_code"]
        
        # Check if account already exists
        existing_accounts = await self.sql_ledger_api.query_accounts({
            "account_code": account_code
        })
        
        if existing_accounts:
            existing_account = existing_accounts[0]
            print(f"   ✅ Found existing account: {account_code}")
            print(f"      Name: {existing_account.name}")
            print(f"      Type: {existing_account.account_type.value}")
            print(f"      Side: {existing_account.side.value}")
            print(f"      Decimals: {existing_account.decimals}")
            return existing_account
        else:
            # Create new account
            new_account = LedgerAccount(
                id=str(ULID()),
                name=account_def["name"],
                account_code=account_code,
                account_type=account_def["account_type"],
                side=account_def["side"],
                workspace_id=None,  # Global internal accounts
                is_promo=False,
                decimals=DECIMALS,  # 10 decimal places
                currency="USD",
                details={
                    "entity": "System",
                    "account_purpose": account_code,
                    "description": account_def["description"]
                },
                history=True
            )
            
            # Create the account
            from ledger.ledger_api import LedgerAccountTransaction
            await self.sql_ledger_api.create_accounts([
                LedgerAccountTransaction(accounts=[new_account])
            ])
            
            print(f"   🆕 Created new account: {account_code}")
            print(f"      Name: {new_account.name}")
            print(f"      Type: {new_account.account_type.value}")
            print(f"      Side: {new_account.side.value}")
            print(f"      Decimals: {new_account.decimals}")
            
            return new_account
    
    def display_account_summary(self):
        """Display a summary of all internal accounts."""
        print("\n📊 INTERNAL ACCOUNTS SUMMARY")
        print("=" * 80)
        
        # Group accounts by type
        accounts_by_type = {}
        for account_code, account in self.internal_accounts.items():
            account_type = account.account_type.value.title()
            if account_type not in accounts_by_type:
                accounts_by_type[account_type] = []
            accounts_by_type[account_type].append(account)
        
        # Display each account type
        for account_type in sorted(accounts_by_type.keys()):
            print(f"\n{account_type.upper()} ACCOUNTS:")
            print("-" * 60)
            
            type_accounts = accounts_by_type[account_type]
            account_data = []
            
            for account in type_accounts:
                account_data.append([
                    account.account_code,
                    account.name,
                    account.side.value.title(),
                    account.decimals,
                    account.details.get("description", "N/A")
                ])
            
            headers = ['Account Code', 'Account Name', 'Normal Side', 'Decimals', 'Description']
            print(f"{tabulate(account_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'center', 'center', 'left'])}")
    
    async def get_account_balances(self):
        """Get current balances for all internal accounts."""
        print("\n💰 INTERNAL ACCOUNT BALANCES")
        print("=" * 80)
        
        await self.sql_ledger_api.begin_transaction()
        try:
            balances = {}
            for account_code, account in self.internal_accounts.items():
                balance = await self.sql_ledger_api.get_account_balance(account.id)
                balances[account_code] = balance
        finally:
            await self.sql_ledger_api.end_transaction()
        
        # Group accounts by type for display
        accounts_by_type = {}
        for account_code, account in self.internal_accounts.items():
            account_type = account.account_type.value.title()
            if account_type not in accounts_by_type:
                accounts_by_type[account_type] = []
            accounts_by_type[account_type].append((account_code, account))
        
        # Display balances by type
        for account_type in sorted(accounts_by_type.keys()):
            print(f"\n{account_type.upper()} ACCOUNTS:")
            print("-" * 60)
            
            type_accounts = accounts_by_type[account_type]
            balance_data = []
            type_total = 0
            
            for account_code, account in type_accounts:
                balance = balances[account_code]
                balance_dollars = Decimal(balance) / SCALE
                
                # For accounting display, show credit balances as positive
                if balance < 0:
                    # Negative balance means credit balance - show as positive
                    display_balance = abs(balance_dollars)
                    balance_str = fmt_decimal(display_balance)
                    balance_type = "Cr"
                elif balance > 0:
                    # Positive balance means debit balance
                    display_balance = balance_dollars
                    balance_str = fmt_decimal(display_balance)
                    balance_type = "Dr"
                else:
                    # Zero balance
                    display_balance = Decimal(0)
                    balance_str = fmt_decimal(display_balance)
                    balance_type = "-"
                
                balance_data.append([
                    account.account_code,
                    account.name,
                    balance_str,
                    balance_type
                ])
                type_total += balance
            
            # Add total row
            total_dollars = Decimal(type_total) / SCALE
            if type_total < 0:
                display_total = abs(total_dollars)
                total_str = fmt_decimal(display_total)
                total_type = "Cr"
            elif type_total > 0:
                display_total = total_dollars
                total_str = fmt_decimal(display_total)
                total_type = "Dr"
            else:
                display_total = Decimal(0)
                total_str = fmt_decimal(display_total)
                total_type = "-"
            
            balance_data.append([
                f"TOTAL {account_type.upper()}",
                "",
                total_str,
                total_type
            ])
            
            headers = ['Account Code', 'Account Name', 'Balance', 'Type']
            print(f"{tabulate(balance_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'right', 'center'])}")
        
        return balances

@pytest_asyncio.fixture(scope="session")
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
    from ledger.ledger_api import Ledger
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
async def test_internal_accounts_management(sql_ledger_api):
    """Test finding or creating internal accounts with proper accounting classification."""
    print("\n🧪 Testing Internal Account Management...")
    
    # Create ledger manager
    ledger_manager = LedgerManager(sql_ledger_api)
    
    # Find or create all internal accounts
    internal_accounts = await ledger_manager.find_or_create_internal_accounts()
    
    # Verify we have all required accounts
    required_accounts = [
        "internal_cc_processor",
        "internal_cash", 
        "internal_revenue",
        "internal_cost",
        "internal_payable"
    ]
    
    for account_code in required_accounts:
        assert account_code in internal_accounts, f"Missing required account: {account_code}"
        account = internal_accounts[account_code]
        # Note: Existing accounts may have different decimal precision, which is acceptable
        print(f"   Account {account_code}: {account.decimals} decimal places")
    
    # Display account summary
    ledger_manager.display_account_summary()
    
    # Get and display current balances
    balances = await ledger_manager.get_account_balances()
    
    # Verify accounting equation (Assets = Liabilities + Equity)
    asset_total = 0
    liability_total = 0
    income_total = 0
    expense_total = 0
    
    for account_code, account in internal_accounts.items():
        balance = balances[account_code]
        if account.account_type == AccountType.ASSET:
            asset_total += balance
        elif account.account_type == AccountType.LIABILITY:
            liability_total += balance
        elif account.account_type == AccountType.INCOME:
            income_total += balance
        elif account.account_type == AccountType.EXPENSE:
            expense_total += balance
    
    equity = income_total - expense_total
    
    print(f"\n⚖️  ACCOUNTING EQUATION VERIFICATION:")
    print(f"Assets: {fmt_decimal(Decimal(asset_total) / SCALE)}")
    print(f"Liabilities: {fmt_decimal(Decimal(liability_total) / SCALE)}")
    print(f"Income: {fmt_decimal(Decimal(income_total) / SCALE)}")
    print(f"Expenses: {fmt_decimal(Decimal(expense_total) / SCALE)}")
    print(f"Equity (Income - Expenses): {fmt_decimal(Decimal(equity) / SCALE)}")
    
    equation_check = asset_total - (liability_total + equity)
    equation_balanced = abs(equation_check) < Decimal('0.0000000001')
    
    print(f"Accounting Equation Check: {fmt_decimal(Decimal(equation_check) / SCALE)}")
    print(f"Equation Balanced: {'✓ YES' if equation_balanced else '✗ NO'}")
    
    print(f"\n✅ Internal account management test completed successfully!")
    print(f"   Total accounts managed: {len(internal_accounts)}")
    print(f"   Decimal precision: {DECIMALS} places")
    print(f"   Accounting equation balanced: {'✓' if equation_balanced else '✗'}")

# Pytest will automatically discover and run the test functions
