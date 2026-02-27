#!/usr/bin/env python3
"""
Simple Transaction Test for Ledger API

This module contains a minimal test for the Ledger API using the transaction builder
with MySQL database.
"""

import os
import sys
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from datetime import datetime, timezone

# Add project root so "dojo" package can be imported
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)
load_dotenv(os.path.join(_root, '.env'))

from dojo.ledger.ledger_api import (
    Ledger,
    LedgerAccount,
    LedgerAccountTransaction,
    LedgerAccountTransfer,
    LedgerLogicalTransaction,
    AccountType,
    LedgerSide,
    generate_account_code,
)
from dojo.ledger.sql_ledger import SQLLedgerAPI
from dojo.ledger.ledger_tx_builder import LedgerTransactionBuilder
from dojo.models.functions import generate_ulid
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine


class TestSimpleTransaction:
    """Simple test for transaction builder integration."""
    
    @pytest.fixture
    def database_url(self):
        """Fixture providing database URL for testing."""
        url = os.environ.get('DATABASE_ASYNC_TEST')
        if not url or 'mysql' not in url:
            pytest.skip("DATABASE_ASYNC_TEST (MySQL) not set or not MySQL")
        return url

    @pytest_asyncio.fixture
    async def check_mysql(self, database_url):
        """Skip entire test class if MySQL is not reachable."""
        try:
            engine = create_async_engine(database_url, echo=False)
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
        except OperationalError as e:
            pytest.skip(f"MySQL server not reachable: {e}")

    @pytest.fixture
    def sql_ledger_api(self, database_url, check_mysql):
        """Fixture providing SQLLedgerAPI instance."""
        ledger = Ledger(
            id=1,
            accounts=[],
            has_journal=True,
            has_transactions=True,
            config={"test": True, "balance_via_trigger": True}  # MySQL uses triggers for balance updates
        )
        return SQLLedgerAPI(ledger, database_url)
    
    @pytest.fixture
    def unique_suffix(self):
        """Unique suffix per test run to avoid duplicate account_code in shared MySQL."""
        return generate_ulid().hex()[:12]

    @pytest.fixture
    def account_id_bytes(self):
        """Binary ULID mapping for test accounts."""
        return {
            "cash": generate_ulid(),
            "ar_processor": generate_ulid(),
            "unearned_revenue": generate_ulid(),
            "revenue_product_a": generate_ulid(),
            "service_fees_expense": generate_ulid(),
            "tax_payable": generate_ulid(),
            "promo_expense": generate_ulid(),
            "promo_liability": generate_ulid(),
            "promo_revenue_product_a": generate_ulid(),
        }

    @pytest.fixture
    def tx_builder(self, account_id_bytes):
        """Fixture providing transaction builder with test account IDs (binary ULIDs)."""
        ids = account_id_bytes
        account_ids = {
            "cash_bank": ids["cash"],
            "ar_processor": ids["ar_processor"],
            "unearned_revenue": ids["unearned_revenue"],
            "revenue_product_a": ids["revenue_product_a"],
            "service_fees_expense": ids["service_fees_expense"],
            "tax_payable": ids["tax_payable"],
            "promo_expense": ids["promo_expense"],
            "promo_liability": ids["promo_liability"],
            "promo_revenue_product_a": ids["promo_revenue_product_a"],
        }
        return LedgerTransactionBuilder(account_ids)

    @pytest.fixture
    def test_accounts(self, account_id_bytes, unique_suffix):
        """Create test accounts for the transaction builder (binary ULIDs)."""
        ids = account_id_bytes
        def code(name, ws=1):
            return f"{generate_account_code(name, ws)}_{unique_suffix}"
        return [
            LedgerAccount(
                id=ids["cash"],
                name="Cash Bank",
                account_code=code("Cash Bank"),
                account_type=AccountType.ASSET,
                side=LedgerSide.DEBIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id=ids["ar_processor"],
                name="AR Processor",
                account_code=code("AR Processor"),
                account_type=AccountType.ASSET,
                side=LedgerSide.DEBIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id=ids["unearned_revenue"],
                name="Unearned Revenue",
                account_code=code("Unearned Revenue"),
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id=ids["revenue_product_a"],
                name="Product A Revenue",
                account_code=code("Product A Revenue"),
                account_type=AccountType.INCOME,
                side=LedgerSide.CREDIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id=ids["service_fees_expense"],
                name="Service Fees Expense",
                account_code=code("Service Fees Expense"),
                account_type=AccountType.EXPENSE,
                side=LedgerSide.DEBIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id=ids["tax_payable"],
                name="Tax Payable",
                account_code=code("Tax Payable"),
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id=ids["promo_expense"],
                name="Promo Expense",
                account_code=code("Promo Expense"),
                account_type=AccountType.EXPENSE,
                side=LedgerSide.DEBIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id=ids["promo_liability"],
                name="Promo Liability",
                account_code=code("Promo Liability"),
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id=ids["promo_revenue_product_a"],
                name="Promo Revenue Product A",
                account_code=code("Promo Revenue Product A"),
                account_type=AccountType.INCOME,
                side=LedgerSide.CREDIT,
                workspace_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            )
        ]
    
    @pytest.mark.asyncio
    async def test_single_payment_transaction(self, sql_ledger_api, tx_builder, test_accounts):
        """Test a single payment transaction built with the transaction builder."""
        print(f"🗄️  Testing single payment transaction with MySQL database")
        
        try:
            # Create accounts
            await sql_ledger_api.begin_transaction()
            await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=test_accounts)])
            await sql_ledger_api.end_transaction()
            
            # Build a payment transaction
            payment_tx = await tx_builder.payment(
                amount=100.00,
                user_id=123,
                name="Test Payment",
                description="Test payment transaction"
            )
            
            # Verify transaction structure
            assert payment_tx.transaction_type.value == "PAYMENT"
            assert payment_tx.user_id == 123
            assert payment_tx.reference == "Test Payment"
            assert payment_tx.description == "Test payment transaction"
            assert len(payment_tx.entries) == 2
            assert len(payment_tx.transfers) == 1
            
            # Verify journal entries
            ar_entry = payment_tx.entries[0]
            revenue_entry = payment_tx.entries[1]
            
            # LedgerTransactionBuilder uses 10 decimal places (SCALE=10^10)
            amount_micro = 100 * 10**10  # $100.00 in micro units
            assert ar_entry.account_id == tx_builder.account_ids["ar_processor"]
            assert ar_entry.debit == amount_micro
            assert ar_entry.credit == 0

            assert revenue_entry.account_id == tx_builder.account_ids["unearned_revenue"]
            assert revenue_entry.debit == 0
            assert revenue_entry.credit == amount_micro

            # Verify transfer
            transfer = payment_tx.transfers[0]
            assert transfer.debit_account_id == tx_builder.account_ids["ar_processor"]
            assert transfer.credit_account_id == tx_builder.account_ids["unearned_revenue"]
            assert transfer.amount == amount_micro
            
            # Get initial balances before the transaction (use account IDs, not key names)
            ar_id = tx_builder.account_ids["ar_processor"]
            unearned_id = tx_builder.account_ids["unearned_revenue"]
            await sql_ledger_api.begin_transaction()
            initial_ar_balance = await sql_ledger_api.get_account_balance(ar_id)
            initial_revenue_balance = await sql_ledger_api.get_account_balance(unearned_id)
            await sql_ledger_api.end_transaction()
            
            # Create the transaction in the database
            logical_tx = LedgerLogicalTransaction(transactions=[payment_tx])
            await sql_ledger_api.begin_transaction()
            await sql_ledger_api.create_transactions([logical_tx])
            await sql_ledger_api.end_transaction()
            
            # Verify accounts were created and balances updated
            await sql_ledger_api.begin_transaction()
            final_ar_balance = await sql_ledger_api.get_account_balance(ar_id)
            final_revenue_balance = await sql_ledger_api.get_account_balance(unearned_id)
            await sql_ledger_api.end_transaction()
            
            # Calculate expected balances (initial + transaction amount)
            expected_ar_balance = initial_ar_balance + amount_micro  # Add $100.00 debit
            expected_revenue_balance = initial_revenue_balance - amount_micro  # Subtract $100.00 credit (liability)
            
            # Check balances (should be updated by triggers)
            assert final_ar_balance == expected_ar_balance, f"AR balance: expected {expected_ar_balance}, got {final_ar_balance}"
            assert final_revenue_balance == expected_revenue_balance, f"Revenue balance: expected {expected_revenue_balance}, got {final_revenue_balance}"
            
            print("✅ Payment transaction created and balances updated successfully")
            
        finally:
            # Clean up database connections
            await sql_ledger_api.close()


if __name__ == "__main__":
    pytest.main([__file__])
