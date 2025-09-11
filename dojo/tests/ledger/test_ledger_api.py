"""
Unit Tests for Ledger API

This module contains comprehensive tests for the Ledger API implementations,
including the SQL backend with various database types.
"""

import os
import sys
import uuid
import pytest
import pytest_asyncio
import tempfile
from typing import List, Dict, Any
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

sys.path.append('../..')

from ledger.ledger_api import (
    LedgerAPI,
    Ledger,
    LedgerAccount,
    LedgerAccountBalance,
    LedgerJournalEntry,
    LedgerTransfer,
    LedgerTransaction,
    LedgerAccountTransaction,
    LedgerTransferTransaction,
    LedgerJournalTransaction,
    LedgerAccountFilter,
    LedgerQuery,
    AccountType,
    LedgerSide,
    TransactionType
)

from ledger.sql_ledger import (
    SQLLedgerAPI,
    SQLAccount,
    SQLAccountBalance,
    SQLTransfer,
    SQLTransaction,
    SQLJournalEntry
)


class TestLedgerAPI:
    """Base test class for LedgerAPI implementations."""
    
    def create_test_ledger(self) -> Ledger:
        """Create a test ledger configuration."""
        return Ledger(
            id=1,
            accounts=[],
            has_journal=True,
            has_transactions=True,
            config={"test": True}
        )
    
    def create_test_accounts(self) -> List[LedgerAccount]:
        """Create test accounts for testing."""
        return [
            LedgerAccount(
                id="cash",
                name="Cash Account",
                account_type=AccountType.ASSET,
                side=LedgerSide.DEBIT,
                owner_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details={"test": "account"},
                history=True
            ),
            LedgerAccount(
                id="revenue",
                name="Revenue Account", 
                account_type=AccountType.INCOME,
                side=LedgerSide.CREDIT,
                owner_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id="expenses",
                name="Expenses Account",
                account_type=AccountType.EXPENSE,
                side=LedgerSide.DEBIT,
                owner_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            )
        ]
    
    def create_test_transfers(self) -> List[LedgerTransfer]:
        """Create test transfers for testing."""
        return [
            LedgerTransfer(
                id=str(uuid.uuid4()),
                debit_account_id="cash",
                credit_account_id="revenue",
                amount=10000,  # $100.00
                ts_created=datetime.now(timezone.utc),
                transaction_id="tx1"
            ),
            LedgerTransfer(
                id=str(uuid.uuid4()),
                debit_account_id="expenses",
                credit_account_id="cash",
                amount=2500,  # $25.00
                ts_created=datetime.now(timezone.utc),
                transaction_id="tx2"
            )
        ]


class TestSQLLedgerAPI(TestLedgerAPI):
    """Test class for SQL Ledger API implementation."""
    
    @pytest.fixture(params=['sqlite'])
    def database_url(self, request):
        """Fixture providing SQLite database URL for testing."""
        if request.param == 'sqlite':
            # Create temporary SQLite database
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
            temp_file.close()
            return f"sqlite+aiosqlite:///{temp_file.name}"
    
    @pytest_asyncio.fixture
    async def sql_ledger_api(self, database_url):
        """Fixture providing SQLLedgerAPI instance."""
        ledger = self.create_test_ledger()
        api = SQLLedgerAPI(ledger, database_url)
        
        # Create tables first
        await api.create_tables()
        
        # Then create SQLite triggers if using SQLite
        if database_url.startswith('sqlite'):
            await api._create_sqlite_triggers()
        yield api
        
        # Cleanup for SQLite
        if database_url.startswith('sqlite'):
            db_path = database_url.replace('sqlite+aiosqlite:///', '')
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    @pytest.mark.asyncio
    async def test_init(self, sql_ledger_api):
        """Test SQLLedgerAPI initialization."""
        assert sql_ledger_api.ledger is not None
        assert sql_ledger_api.engine is not None
        assert sql_ledger_api.SessionLocal is not None
    
    @pytest.mark.asyncio
    async def test_begin_end_transaction(self, sql_ledger_api):
        """Test transaction lifecycle."""
        # Test begin transaction
        await sql_ledger_api.begin_transaction()
        assert sql_ledger_api._session is not None
        
        # Test end transaction
        await sql_ledger_api.end_transaction()
        assert sql_ledger_api._session is None
    
    @pytest.mark.asyncio
    async def test_begin_transaction_twice_raises_error(self, sql_ledger_api):
        """Test that beginning a transaction twice raises an error."""
        await sql_ledger_api.begin_transaction()
        
        with pytest.raises(RuntimeError, match="Transaction already active"):
            await sql_ledger_api.begin_transaction()
        
        await sql_ledger_api.end_transaction()
    
    @pytest.mark.asyncio
    async def test_end_transaction_without_begin_raises_error(self, sql_ledger_api):
        """Test that ending a transaction without begin raises an error."""
        with pytest.raises(RuntimeError, match="No active transaction"):
            await sql_ledger_api.end_transaction()
    
    @pytest.mark.asyncio
    async def test_rollback_transaction(self, sql_ledger_api):
        """Test transaction rollback."""
        await sql_ledger_api.begin_transaction()
        assert sql_ledger_api._session is not None
        
        await sql_ledger_api.cancel_transaction()
        assert sql_ledger_api._session is None
    
    @pytest.mark.asyncio
    async def test_create_accounts(self, sql_ledger_api):
        """Test creating accounts."""
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        # Verify accounts were created
        await sql_ledger_api.begin_transaction()
        retrieved_accounts = await sql_ledger_api.lookup_accounts(["cash", "revenue", "expenses"])
        await sql_ledger_api.end_transaction()
        
        assert len(retrieved_accounts) == 3
        assert any(acc.id == "cash" for acc in retrieved_accounts)
        assert any(acc.id == "revenue" for acc in retrieved_accounts)
        assert any(acc.id == "expenses" for acc in retrieved_accounts)
    
    @pytest.mark.asyncio
    async def test_create_transfers(self, sql_ledger_api):
        """Test creating transfers."""
        # First create accounts
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        # Then create transfers
        transfers = self.create_test_transfers()
        transfer_transactions = [LedgerTransferTransaction(transfers=transfers)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_transfers(transfer_transactions)
        await sql_ledger_api.end_transaction()
        
        # Verify transfers were created
        await sql_ledger_api.begin_transaction()
        transfer_ids = [t.id for t in transfers]
        retrieved_transfers = await sql_ledger_api.lookup_transfers(transfer_ids)
        await sql_ledger_api.end_transaction()
        
        assert len(retrieved_transfers) == 2
    
    @pytest.mark.asyncio
    async def test_account_balance_updates(self, sql_ledger_api):
        """Test that account balances are updated by triggers."""
        # Create accounts
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        # Check initial balances
        await sql_ledger_api.begin_transaction()
        cash_balance = await sql_ledger_api.get_account_balance("cash")
        revenue_balance = await sql_ledger_api.get_account_balance("revenue")
        await sql_ledger_api.end_transaction()
        
        assert cash_balance == 0
        assert revenue_balance == 0
        
        # Create a transfer
        transfer = LedgerTransfer(
            id=str(uuid.uuid4()),
            debit_account_id="cash",      # Cash increases (debit)
            credit_account_id="revenue",  # Revenue increases (credit)
            amount=10000,  # $100.00
            ts_created=datetime.now(timezone.utc),
            transaction_id="tx1"
        )
        
        transfer_transactions = [LedgerTransferTransaction(transfers=[transfer])]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_transfers(transfer_transactions)
        await sql_ledger_api.end_transaction()
        
        # Check updated balances
        await sql_ledger_api.begin_transaction()
        cash_balance = await sql_ledger_api.get_account_balance("cash")
        revenue_balance = await sql_ledger_api.get_account_balance("revenue")
        await sql_ledger_api.end_transaction()
        
        # In the transfer, revenue is the source (credit account), so it loses money
        # Cash is the destination (debit account), so it gains money
        assert cash_balance == 10000   # Cash gained $100
        assert revenue_balance == -10000  # Revenue lost $100 (should actually be credited)
    
    @pytest.mark.asyncio
    async def test_query_accounts(self, sql_ledger_api):
        """Test querying accounts."""
        # Create accounts
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        # Query by account ID
        await sql_ledger_api.begin_transaction()
        query: LedgerQuery = {"account_id": "cash"}
        results = await sql_ledger_api.query_accounts(query)
        await sql_ledger_api.end_transaction()
        
        assert len(results) == 1
        assert results[0].id == "cash"
        assert results[0].name == "Cash Account"
        
        # Query by owner ID
        await sql_ledger_api.begin_transaction()
        query = {"owner_id": 1}
        results = await sql_ledger_api.query_accounts(query)
        await sql_ledger_api.end_transaction()
        
        assert len(results) == 3
    
    @pytest.mark.asyncio
    async def test_query_transfers(self, sql_ledger_api):
        """Test querying transfers."""
        # Setup accounts and transfers
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        transfers = self.create_test_transfers()
        transfer_transactions = [LedgerTransferTransaction(transfers=transfers)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_transfers(transfer_transactions)
        await sql_ledger_api.end_transaction()
        
        # Query by account ID
        await sql_ledger_api.begin_transaction()
        query: LedgerQuery = {"account_id": "cash"}
        results = await sql_ledger_api.query_transfers(query)
        await sql_ledger_api.end_transaction()
        
        # Cash should be involved in both transfers
        assert len(results) == 2
    
    @pytest.mark.asyncio
    async def test_get_account_transfers(self, sql_ledger_api):
        """Test getting transfers for a specific account."""
        # Setup accounts and transfers
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        transfers = self.create_test_transfers()
        transfer_transactions = [LedgerTransferTransaction(transfers=transfers)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_transfers(transfer_transactions)
        await sql_ledger_api.end_transaction()
        
        # Get transfers for cash account
        await sql_ledger_api.begin_transaction()
        filter: LedgerAccountFilter = {
            "account_id": "cash",
            "limit": 10
        }
        results = await sql_ledger_api.get_account_transfers(filter)
        await sql_ledger_api.end_transaction()
        
        assert len(results) == 2
    
    @pytest.mark.asyncio
    async def test_create_journal_entries(self, sql_ledger_api):
        """Test creating journal entries."""
        # Create accounts first
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        # Create journal entries
        entries = [
            LedgerJournalEntry(
                id=str(uuid.uuid4()),
                account_id="cash",
                debit=10000,
                credit=None,
                ts_created=datetime.now(timezone.utc),
                transaction_id="tx1",
                description="Cash debit"
            ),
            LedgerJournalEntry(
                id=str(uuid.uuid4()),
                account_id="revenue",
                debit=None,
                credit=10000,
                ts_created=datetime.now(timezone.utc),
                transaction_id="tx1",
                description="Revenue credit"
            )
        ]
        
        entry_transactions = [LedgerJournalTransaction(entries=entries)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_journal_entries(entry_transactions)
        await sql_ledger_api.end_transaction()
        
        # Verify entries were created
        await sql_ledger_api.begin_transaction()
        entry_ids = [e.id for e in entries]
        retrieved_entries = await sql_ledger_api.lookup_entries(entry_ids)
        await sql_ledger_api.end_transaction()
        
        assert len(retrieved_entries) == 2
    
    @pytest.mark.asyncio
    async def test_query_journal(self, sql_ledger_api):
        """Test querying journal entries."""
        # Setup accounts and journal entries
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        entries = [
            LedgerJournalEntry(
                id=str(uuid.uuid4()),
                account_id="cash",
                debit=10000,
                credit=None,
                ts_created=datetime.now(timezone.utc),
                transaction_id="tx1",
                description="Cash debit"
            )
        ]
        
        entry_transactions = [LedgerJournalTransaction(entries=entries)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_journal_entries(entry_transactions)
        await sql_ledger_api.end_transaction()
        
        # Query by account ID
        await sql_ledger_api.begin_transaction()
        query: LedgerQuery = {"account_id": "cash"}
        results = await sql_ledger_api.query_journal(query)
        await sql_ledger_api.end_transaction()
        
        assert len(results) == 1
        assert results[0].account_id == "cash"
        assert results[0].debit == 10000
    
    @pytest.mark.asyncio
    async def test_get_account_balances_history(self, sql_ledger_api):
        """Test getting account balance history."""
        # Create accounts
        accounts = self.create_test_accounts()
        account_transactions = [LedgerAccountTransaction(accounts=accounts)]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_accounts(account_transactions)
        await sql_ledger_api.end_transaction()
        
        # Create a transfer to generate balance history
        transfer = LedgerTransfer(
            id=str(uuid.uuid4()),
            debit_account_id="cash",
            credit_account_id="revenue",
            amount=10000,
            ts_created=datetime.now(timezone.utc),
            transaction_id="tx1"
        )
        
        transfer_transactions = [LedgerTransferTransaction(transfers=[transfer])]
        
        await sql_ledger_api.begin_transaction()
        await sql_ledger_api.create_transfers(transfer_transactions)
        await sql_ledger_api.end_transaction()
        
        # Get balance history for cash account
        await sql_ledger_api.begin_transaction()
        filter: LedgerAccountFilter = {
            "account_id": "cash",
            "limit": 10
        }
        results = await sql_ledger_api.get_account_balances(filter)
        await sql_ledger_api.end_transaction()
        
        # Should have balance history entries
        assert len(results) >= 1
        
    @pytest.mark.asyncio
    async def test_conversion_methods(self, sql_ledger_api):
        """Test conversion methods between SQL models and Pydantic models."""
        
        # Test account conversion
        sql_account = SQLAccount(
            id="test_account",
            name="Test Account",
            account_type="asset",
            side="debit",
            owner_id=1,
            is_promo=False,
            decimals=2,
            currency="USD",
            details='{"test": true}',
            history=True,
            balance=1000
        )
        
        ledger_account = sql_ledger_api._convert_sql_account_to_ledger_account(sql_account)
        assert ledger_account.id == "test_account"
        assert ledger_account.name == "Test Account"
        assert ledger_account.account_type == AccountType.ASSET
        assert ledger_account.side == LedgerSide.DEBIT
        assert ledger_account.details == {"test": True}
        
        # Test transfer conversion
        sql_transfer = SQLTransfer(
            id="test_transfer",
            debit_account_id="account1",
            credit_account_id="account2",
            amount=5000,
            ts_created=datetime.now(timezone.utc),
            transaction_id="tx1"
        )
        
        ledger_transfer = await sql_ledger_api._convert_sql_transfer_to_ledger_transfer(sql_transfer, with_balance=False)
        assert ledger_transfer.id == "test_transfer"
        assert ledger_transfer.debit_account_id == "account1"
        assert ledger_transfer.credit_account_id == "account2"
        assert ledger_transfer.amount == 5000
        
        # Test journal entry conversion
        sql_entry = SQLJournalEntry(
            id="test_entry",
            account_id="account1",
            debit=1000,
            credit=None,
            ts_created=datetime.now(timezone.utc),
            transaction_id="tx1",
            description="Test entry"
        )
        
        ledger_entry = sql_ledger_api._convert_sql_entry_to_ledger_entry(sql_entry)
        assert ledger_entry.id == "test_entry"
        assert ledger_entry.account_id == "account1"
        assert ledger_entry.debit == 1000
        assert ledger_entry.credit is None
    
    @pytest.mark.asyncio
    async def test_error_handling(self, sql_ledger_api):
        """Test error handling scenarios."""
        # Test get_session without active transaction
        with pytest.raises(RuntimeError, match="No active transaction"):
            sql_ledger_api.get_session()
        
        # Test lookup on non-existent accounts
        await sql_ledger_api.begin_transaction()
        results = await sql_ledger_api.lookup_accounts(["non_existent"])
        await sql_ledger_api.end_transaction()
        
        assert len(results) == 0
        
        # Test get_account_balance for non-existent account
        await sql_ledger_api.begin_transaction()
        balance = await sql_ledger_api.get_account_balance("non_existent")
        await sql_ledger_api.end_transaction()
        
        assert balance == 0


class TestLedgerModels:
    """Test the Pydantic models used in the Ledger API."""
    
    def test_ledger_account_creation(self):
        """Test creating a LedgerAccount."""
        account = LedgerAccount(
            id="test_account",
            name="Test Account",
            account_type=AccountType.ASSET,
            side=LedgerSide.DEBIT,
            owner_id=1,
            is_promo=False,
            decimals=2,
            currency="USD",
            details={"test": True},
            history=True
        )
        
        assert account.id == "test_account"
        assert account.name == "Test Account"
        assert account.account_type == AccountType.ASSET
        assert account.side == LedgerSide.DEBIT
        assert account.owner_id == 1
        assert account.is_promo is False
        assert account.decimals == 2
        assert account.currency == "USD"
        assert account.details == {"test": True}
        assert account.history is True
    
    def test_ledger_transfer_creation(self):
        """Test creating a LedgerTransfer."""
        test_timestamp = datetime.now(timezone.utc)
        transfer = LedgerTransfer(
            id="test_transfer",
            debit_account_id="account1",
            credit_account_id="account2",
            amount=10000,
            ts_created=test_timestamp,
            transaction_id="tx1"
        )
        
        assert transfer.id == "test_transfer"
        assert transfer.debit_account_id == "account1"
        assert transfer.credit_account_id == "account2"
        assert transfer.amount == 10000
        assert transfer.ts_created == test_timestamp
        assert transfer.transaction_id == "tx1"
    
    def test_ledger_transaction_creation(self):
        """Test creating a LedgerTransaction."""
        transaction = LedgerTransaction(
            id=1,
            transaction_type=TransactionType.PAYMENT,
            entries=None,
            transfers=[],
            ts_created=datetime.now(timezone.utc),
            user_id=1,
            reference="REF123",
            description="Test transaction",
            details={"test": True}
        )
        
        assert transaction.id == 1
        assert transaction.transaction_type == TransactionType.PAYMENT
        assert transaction.entries is None
        assert transaction.transfers == []
        assert transaction.user_id == 1
        assert transaction.reference == "REF123"
        assert transaction.description == "Test transaction"
        assert transaction.details == {"test": True}
    
    def test_account_type_enum(self):
        """Test AccountType enum values."""
        assert AccountType.ASSET.value == "asset"
        assert AccountType.LIABILITY.value == "liability"
        assert AccountType.INCOME.value == "income"
        assert AccountType.EXPENSE.value == "expense"
    
    def test_ledger_side_enum(self):
        """Test LedgerSide enum values."""
        assert LedgerSide.DEBIT.value == "debit"
        assert LedgerSide.CREDIT.value == "credit"
    
    def test_transaction_type_enum(self):
        """Test TransactionType enum values."""
        assert TransactionType.PAYMENT.value == "PAYMENT"
        assert TransactionType.PURCHASE.value == "PURCHASE"
        assert TransactionType.SETTLEMENT.value == "SETTLEMENT"
        assert TransactionType.EXPENSE.value == "EXPENSE"
        assert TransactionType.TAX.value == "TAX"
        assert TransactionType.TAX_REMIT.value == "TAX_REMIT"
        assert TransactionType.REFUND.value == "REFUND"
        assert TransactionType.PROMO.value == "PROMO"
        assert TransactionType.USE_PROMO.value == "USE_PROMO"
        assert TransactionType.CANCEL_PROMO.value == "CANCEL_PROMO"


class TestSQLLedgerIntegration:
    """Integration tests for the SQL Ledger API."""
    
    @pytest.mark.asyncio
    async def test_complete_accounting_workflow(self):
        """Test a complete accounting workflow with multiple transactions."""
        # Create a temporary SQLite database
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        database_url = f"sqlite+aiosqlite:///{temp_file.name}"

        print(f"🗄️  Creating SQLite database: {temp_file.name}")
        
        try:
            # Initialize ledger
            ledger = Ledger(
                id=1,
                accounts=[],
                has_journal=True,
                has_transactions=True,
                config={"name": "Test Ledger"}
            )
            
            api = SQLLedgerAPI(ledger, database_url)
            
            # Initialize database tables and triggers
            await api.create_tables()
            await api._create_sqlite_triggers()
            
            # Create accounts
            accounts = [
                LedgerAccount(
                    id="cash",
                    name="Cash",
                    account_type=AccountType.ASSET,
                    side=LedgerSide.DEBIT,
                    owner_id=1,
                    is_promo=False,
                    decimals=2,
                    currency="USD",
                    details=None,
                    history=True
                ),
                LedgerAccount(
                    id="sales",
                    name="Sales Revenue",
                    account_type=AccountType.INCOME,
                    side=LedgerSide.CREDIT,
                    owner_id=1,
                    is_promo=False,
                    decimals=2,
                    currency="USD",
                    details=None,
                    history=True
                ),
                LedgerAccount(
                    id="expenses",
                    name="Operating Expenses",
                    account_type=AccountType.EXPENSE,
                    side=LedgerSide.DEBIT,
                    owner_id=1,
                    is_promo=False,
                    decimals=2,
                    currency="USD",
                    details=None,
                    history=True
                )
            ]
            
            # Create accounts
            await api.begin_transaction()
            await api.create_accounts([LedgerAccountTransaction(accounts=accounts)])
            await api.end_transaction()
            
            # Create transfers
            transfers = [
                # Sale: Cash increases, Sales revenue increases
                LedgerTransfer(
                    id=str(uuid.uuid4()),
                    debit_account_id="cash",
                    credit_account_id="sales",
                    amount=50000,  # $500.00
                    ts_created=datetime.now(timezone.utc),
                    transaction_id="sale_1"
                ),
                # Expense: Expenses increase, Cash decreases
                LedgerTransfer(
                    id=str(uuid.uuid4()),
                    debit_account_id="expenses",
                    credit_account_id="cash",
                    amount=15000,  # $150.00
                    ts_created=datetime.now(timezone.utc),
                    transaction_id="expense_1"
                )
            ]
            
            await api.begin_transaction()
            await api.create_transfers([LedgerTransferTransaction(transfers=transfers)])
            await api.end_transaction()
            
            # Check final balances
            await api.begin_transaction()
            cash_balance = await api.get_account_balance("cash")
            sales_balance = await api.get_account_balance("sales")
            expenses_balance = await api.get_account_balance("expenses")
            await api.end_transaction()
            
            # Expected balances:
            # Cash: +500 - 150 = +350
            # Sales: -500 (credit account, so negative balance means positive revenue)
            # Expenses: +150
            assert cash_balance == 35000   # $350.00
            assert sales_balance == -50000  # -$500.00 (credit balance)
            assert expenses_balance == 15000  # $150.00
            
            # Query account history
            await api.begin_transaction()
            cash_history = await api.get_account_balances({"account_id": "cash", "limit": 10})
            await api.end_transaction()
            
            # Should have balance history from the transfers
            assert len(cash_history) >= 2
            
        finally:
            pass
        #    # Cleanup
        #    if os.path.exists(temp_file.name):
        #        os.unlink(temp_file.name)


if __name__ == "__main__":
    pytest.main([__file__]) 
