#!/usr/bin/env python3
"""
Simple Transaction Test for Ledger API

This module contains a minimal test for the Ledger API using the transaction builder
with MySQL database.
"""

import os
import sys
import pytest
from dotenv import load_dotenv
from datetime import datetime, timezone

sys.path.append('../..')
load_dotenv('../../../.env')

from ledger.ledger_api import (
    Ledger,
    LedgerAccount,
    LedgerAccountTransaction,
    LedgerAccountTransfer,
    LedgerLogicalTransaction,
    AccountType,
    LedgerSide,
)
from ledger.sql_ledger import SQLLedgerAPI
from ledger.ledger_tx_builder import LedgerTransactionBuilder


class TestSimpleTransaction:
    """Simple test for transaction builder integration."""
    
    @pytest.fixture
    def database_url(self):
        """Fixture providing database URL for testing."""
        return os.environ['DATABASE_ASYNC_TEST']
    
    @pytest.fixture
    def sql_ledger_api(self, database_url):
        """Fixture providing SQLLedgerAPI instance."""
        ledger = Ledger(
            id=1,
            accounts=[],
            has_journal=True,
            has_transactions=True,
            config={"test": True}
        )
        return SQLLedgerAPI(ledger, database_url)
    
    @pytest.fixture
    def tx_builder(self):
        """Fixture providing transaction builder with test account IDs."""
        account_ids = {
            "cash_bank": "cash",
            "ar_processor": "ar_processor", 
            "unearned_revenue": "unearned_revenue",
            "revenue_product_a": "revenue_product_a",
            "service_fees_expense": "service_fees_expense",
            "tax_payable": "tax_payable",
            "promo_expense": "promo_expense",
            "promo_liability": "promo_liability",
            "promo_revenue_product_a": "promo_revenue_product_a"
        }
        return LedgerTransactionBuilder(account_ids)
    
    @pytest.fixture
    def test_accounts(self):
        """Create test accounts for the transaction builder."""
        return [
            LedgerAccount(
                id="cash",
                name="Cash Bank",
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
                id="ar_processor",
                name="AR Processor",
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
                id="unearned_revenue",
                name="Unearned Revenue",
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                owner_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id="revenue_product_a",
                name="Product A Revenue",
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
                id="service_fees_expense",
                name="Service Fees Expense",
                account_type=AccountType.EXPENSE,
                side=LedgerSide.DEBIT,
                owner_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id="tax_payable",
                name="Tax Payable",
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                owner_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id="promo_expense",
                name="Promo Expense",
                account_type=AccountType.EXPENSE,
                side=LedgerSide.DEBIT,
                owner_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id="promo_liability",
                name="Promo Liability",
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                owner_id=1,
                is_promo=False,
                decimals=2,
                currency="USD",
                details=None,
                history=True
            ),
            LedgerAccount(
                id="promo_revenue_product_a",
                name="Promo Revenue Product A",
                account_type=AccountType.INCOME,
                side=LedgerSide.CREDIT,
                owner_id=1,
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
            
            assert ar_entry.account_id == "ar_processor"
            assert ar_entry.debit == 100000000  # $100.00 in micro units
            assert ar_entry.credit == 0
            
            assert revenue_entry.account_id == "unearned_revenue"
            assert revenue_entry.debit == 0
            assert revenue_entry.credit == 100000000  # $100.00 in micro units
            
            # Verify transfer
            transfer = payment_tx.transfers[0]
            assert transfer.debit_account_id == "ar_processor"
            assert transfer.credit_account_id == "unearned_revenue"
            assert transfer.amount == 100000000  # $100.00 in micro units
            
            # Get initial balances before the transaction
            await sql_ledger_api.begin_transaction()
            initial_ar_balance = await sql_ledger_api.get_account_balance("ar_processor")
            initial_revenue_balance = await sql_ledger_api.get_account_balance("unearned_revenue")
            await sql_ledger_api.end_transaction()
            
            # Create the transaction in the database
            logical_tx = LedgerLogicalTransaction(transactions=[payment_tx])
            await sql_ledger_api.begin_transaction()
            await sql_ledger_api.create_transactions([logical_tx])
            await sql_ledger_api.end_transaction()
            
            # Verify accounts were created and balances updated
            await sql_ledger_api.begin_transaction()
            final_ar_balance = await sql_ledger_api.get_account_balance("ar_processor")
            final_revenue_balance = await sql_ledger_api.get_account_balance("unearned_revenue")
            await sql_ledger_api.end_transaction()
            
            # Calculate expected balances (initial + transaction amount)
            expected_ar_balance = initial_ar_balance + 100000000  # Add $100.00 debit
            expected_revenue_balance = initial_revenue_balance - 100000000  # Subtract $100.00 credit (liability)
            
            # Check balances (should be updated by triggers)
            assert final_ar_balance == expected_ar_balance, f"AR balance: expected {expected_ar_balance}, got {final_ar_balance}"
            assert final_revenue_balance == expected_revenue_balance, f"Revenue balance: expected {expected_revenue_balance}, got {final_revenue_balance}"
            
            print("✅ Payment transaction created and balances updated successfully")
            
        finally:
            # Clean up database connections
            await sql_ledger_api.close()


if __name__ == "__main__":
    pytest.main([__file__])
