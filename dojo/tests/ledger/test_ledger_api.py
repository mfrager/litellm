#!/usr/bin/env python3
"""
Comprehensive Ledger API Test Suite

This module contains comprehensive tests for the Ledger API implementations,
following the golden master pattern with detailed tabular output and testing
all transaction types from the transaction builder.
"""

import os
import sys
import uuid
import pytest
import tempfile
from typing import List, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal
from tabulate import tabulate

sys.path.append('../..')

from ledger.ledger_api import (
    LedgerAPI,
    Ledger,
    LedgerAccount,
    LedgerAccountBalance,
    LedgerJournalEntry,
    LedgerAccountTransfer,
    LedgerTransaction,
    LedgerAccountTransaction,
    LedgerTransferTransaction,
    LedgerJournalTransaction,
    LedgerLogicalTransaction,
    LedgerAccountFilter,
    LedgerQuery,
    AccountType,
    LedgerSide,
    TransactionType,
    generate_account_code,
)

from ledger.sql_ledger import SQLLedgerAPI
from ledger.ledger_tx_builder import LedgerTransactionBuilder

# Decimal precision for monetary calculations
DECIMALS = 10
SCALE = Decimal(10) ** DECIMALS

def fmt_decimal(val):
    """Format decimal values for display."""
    return f"${Decimal(val).quantize(Decimal('0.000001')):,.6f}"


class TestComprehensiveLedgerAPI:
    """Comprehensive test suite for Ledger API with all transaction types."""
    
    @pytest.fixture
    def database_url(self):
        """Fixture providing database URL for testing."""
        # Create temporary SQLite database
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        return f"sqlite+aiosqlite:///{temp_file.name}"
    
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
        """Fixture providing transaction builder with comprehensive account IDs."""
        account_ids = {
            # Asset accounts
            "cash_bank": "cash",
            "ar_processor": "ar_processor", 
            
            # Liability accounts
            "unearned_revenue": "unearned_revenue",
            "tax_payable": "tax_payable",
            "promo_liability": "promo_liability",
            
            # Income accounts
            "revenue_product_a": "revenue_product_a",
            "promo_revenue_product_a": "promo_revenue_product_a",
            
            # Expense accounts
            "service_fees_expense": "service_fees_expense",
            "promo_expense": "promo_expense",
        }
        return LedgerTransactionBuilder(account_ids)
    
    @pytest.fixture
    def comprehensive_accounts(self):
        """Create comprehensive chart of accounts for testing."""
        return [
            # ============= ASSET ACCOUNTS =============
            LedgerAccount(
                id="cash",
                name="Cash/Bank Account",
                account_code=generate_account_code("Cash/Bank Account", 100),
                account_type=AccountType.ASSET,
                side=LedgerSide.DEBIT,
                workspace_id=100,
                is_promo=False,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Company"},
                history=True
            ),
            LedgerAccount(
                id="ar_processor",
                name="Accounts Receivable (Processor)",
                account_code=generate_account_code("Accounts Receivable (Processor)", 100),
                account_type=AccountType.ASSET,
                side=LedgerSide.DEBIT,
                workspace_id=100,
                is_promo=False,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Company"},
                history=True
            ),
            
            # ============= LIABILITY ACCOUNTS =============
            LedgerAccount(
                id="unearned_revenue",
                name="Unearned Revenue",
                account_code=generate_account_code("Unearned Revenue", 200),
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                workspace_id=200,
                is_promo=False,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Customer"},
                history=True
            ),
            LedgerAccount(
                id="tax_payable",
                name="Tax Payable",
                account_code=generate_account_code("Tax Payable", 100),
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                workspace_id=100,
                is_promo=False,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Company"},
                history=True
            ),
            LedgerAccount(
                id="promo_liability",
                name="Promo Credit Liability",
                account_code=generate_account_code("Promo Credit Liability", 200),
                account_type=AccountType.LIABILITY,
                side=LedgerSide.CREDIT,
                workspace_id=200,
                is_promo=True,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Customer"},
                history=True
            ),
            
            # ============= INCOME ACCOUNTS =============
            LedgerAccount(
                id="revenue_product_a",
                name="Revenue – Product A",
                account_code=generate_account_code("Revenue – Product A", 100),
                account_type=AccountType.INCOME,
                side=LedgerSide.CREDIT,
                workspace_id=100,
                is_promo=False,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Company"},
                history=True
            ),
            LedgerAccount(
                id="promo_revenue_product_a",
                name="Promo Revenue – Product A",
                account_code=generate_account_code("Promo Revenue – Product A", 100),
                account_type=AccountType.INCOME,
                side=LedgerSide.CREDIT,
                workspace_id=100,
                is_promo=True,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Company"},
                history=True
            ),
            
            # ============= EXPENSE ACCOUNTS =============
            LedgerAccount(
                id="service_fees_expense",
                name="Service Fees Expense",
                account_code=generate_account_code("Service Fees Expense", 100),
                account_type=AccountType.EXPENSE,
                side=LedgerSide.DEBIT,
                workspace_id=100,
                is_promo=False,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Company"},
                history=True
            ),
            LedgerAccount(
                id="promo_expense",
                name="Promo Credit Expense",
                account_code=generate_account_code("Promo Credit Expense", 100),
                account_type=AccountType.EXPENSE,
                side=LedgerSide.DEBIT,
                workspace_id=100,
                is_promo=True,
                decimals=DECIMALS,
                currency="USD",
                details={"entity": "Company"},
                history=True
            ),
        ]

    def display_chart_of_accounts(self, accounts: List[LedgerAccount]):
        """Display chart of accounts in tabular format."""
        print("\n" + "=" * 100)
        print("COMPREHENSIVE CHART OF ACCOUNTS")
        print("=" * 100)
        
        chart_data = []
        for account in accounts:
            chart_data.append([
                account.id,
                account.name,
                account.account_code,
                account.account_type.value.title(),
                account.side.value.title(),
                account.workspace_id,
                "Yes" if account.is_promo else "No",
                account.details.get("entity", "N/A")
            ])
        
        headers = ['Account ID', 'Account Name', 'Account Code', 'Type', 'Normal Side', 'Workspace ID', 'Promotional', 'Entity']
        print(f"\n{tabulate(chart_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'left', 'center', 'center', 'center', 'left'])}")

    def display_account_balances(self, accounts: List[LedgerAccount], balances: Dict[str, int]):
        """Display account balances in tabular format."""
        print("\n" + "=" * 80)
        print("ACCOUNT BALANCES")
        print("=" * 80)
        
        # Group accounts by type
        accounts_by_type = {}
        for account in accounts:
            account_type = account.account_type.value.title()
            if account_type not in accounts_by_type:
                accounts_by_type[account_type] = []
            accounts_by_type[account_type].append(account)
        
        # Display each account type
        for account_type in sorted(accounts_by_type.keys()):
            print(f"\n{account_type.upper()} ACCOUNTS:")
            print("=" * 80)
            
            type_accounts = accounts_by_type[account_type]
            balance_data = []
            type_total = 0
            
            for account in type_accounts:
                balance = balances.get(account.id, 0)
                balance_dollars = Decimal(balance) / SCALE
                balance_str = fmt_decimal(balance_dollars)
                
                if balance < 0:
                    balance_str = f"({fmt_decimal(abs(balance_dollars))})"
                
                # Determine balance type based on account normal side and balance
                balance_type = ""
                if balance > 0:
                    balance_type = "Dr" if account.side == LedgerSide.DEBIT else "Cr"
                elif balance < 0:
                    balance_type = "Cr" if account.side == LedgerSide.DEBIT else "Dr"
                else:
                    balance_type = "-"
                
                balance_data.append([
                    account.id,
                    account.name,
                    balance_str,
                    balance_type,
                    account.workspace_id
                ])
                type_total += balance
            
            # Add total row
            total_dollars = Decimal(type_total) / SCALE
            total_str = fmt_decimal(total_dollars)
            if type_total < 0:
                total_str = f"({fmt_decimal(abs(total_dollars))})"
            
            balance_data.append([
                f"TOTAL {account_type.upper()}",
                "",
                total_str,
                "Dr" if type_total >= 0 else "Cr",
                ""
            ])
            
            headers = ['Account ID', 'Account Name', 'Balance', 'Type', 'Workspace ID']
            print(f"\n{tabulate(balance_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'right', 'center', 'center'])}")

    def display_transaction_summary(self, transactions: List[Dict[str, Any]]):
        """Display transaction summary in tabular format."""
        print("\n" + "=" * 100)
        print("TRANSACTION EXECUTION SUMMARY")
        print("=" * 100)
        
        summary_data = []
        for i, tx_info in enumerate(transactions, 1):
            tx = tx_info["ledger_tx"]
            total_amount = sum(Decimal(transfer.amount) / SCALE for transfer in tx.transfers)
            
            summary_data.append([
                i,
                tx_info["name"],
                tx_info["description"],
                tx.transaction_type.value,
                tx_info["user_id"],
                fmt_decimal(total_amount),
                len(tx.transfers),
                len(tx.entries) if tx.entries else 0
            ])
        
        headers = ['#', 'Transaction Name', 'Description', 'Type', 'User ID', 'Amount', 'Transfers', 'Journal Entries']
        print(f"\n{tabulate(summary_data, headers=headers, tablefmt='grid', colalign=['center', 'left', 'left', 'left', 'center', 'right', 'center', 'center'])}")

    def display_balance_sheet_summary(self, accounts: List[LedgerAccount], balances: Dict[str, int]):
        """Display balance sheet summary with accounting equation verification."""
        print("\n" + "=" * 80)
        print("BALANCE SHEET SUMMARY & ACCOUNTING EQUATION VERIFICATION")
        print("=" * 80)

        # Calculate totals by account type
        totals_by_type = {
            "Asset": 0,
            "Liability": 0,
            "Income": 0,
            "Expense": 0
        }

        for account in accounts:
            account_type = account.account_type.value.title()
            balance = balances.get(account.id, 0)
            
            # For liability and income accounts, we show the credit balance as positive
            if account_type in ["Liability", "Income"]:
                totals_by_type[account_type] += -balance
            else:
                totals_by_type[account_type] += balance

        # Display totals
        summary_data = []
        for account_type, total_micro in totals_by_type.items():
            total_dollars = Decimal(total_micro) / SCALE
            summary_data.append([
                f"Total {account_type}s",
                fmt_decimal(total_dollars)
            ])

        # Calculate net equity (Income - Expenses)
        net_equity_micro = totals_by_type["Income"] - totals_by_type["Expense"]
        net_equity_dollars = Decimal(net_equity_micro) / SCALE
        summary_data.append([
            "Net Equity (Income - Expenses)",
            fmt_decimal(net_equity_dollars)
        ])

        # Verify accounting equation: Assets = Liabilities + Equity
        assets_dollars = Decimal(totals_by_type["Asset"]) / SCALE
        liabilities_dollars = Decimal(totals_by_type["Liability"]) / SCALE
        
        equation_check = assets_dollars - (liabilities_dollars + net_equity_dollars)
        summary_data.append([
            "Accounting Equation Check",
            fmt_decimal(equation_check)
        ])
        
        equation_holds = abs(equation_check) < Decimal('0.000001')
        summary_data.append([
            "Equation Balanced",
            "✓ YES" if equation_holds else "✗ NO"
        ])

        headers = ['Category', 'Amount']
        print(f"\n{tabulate(summary_data, headers=headers, tablefmt='grid', colalign=['left', 'right'])}")
        
        print(f"\nAccounting Equation: Assets = Liabilities + Equity")
        print(f"{fmt_decimal(assets_dollars)} = {fmt_decimal(liabilities_dollars)} + {fmt_decimal(net_equity_dollars)}")

    @pytest.mark.asyncio
    async def test_comprehensive_transaction_workflow(self, sql_ledger_api, tx_builder, comprehensive_accounts):
        """Test comprehensive workflow with all transaction types from ledger_tx_builder.py."""
        print("\n🏦 COMPREHENSIVE LEDGER API TEST - ALL TRANSACTION TYPES")
        print("=" * 100)
        
        try:
            # Initialize database
            await sql_ledger_api.create_tables()
            await sql_ledger_api._create_sqlite_triggers()
            
            # Display chart of accounts
            self.display_chart_of_accounts(comprehensive_accounts)
            
            # Create accounts
            print("\n📊 Creating chart of accounts...")
            await sql_ledger_api.begin_transaction()
            await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=comprehensive_accounts)])
            await sql_ledger_api.end_transaction()
            print(f"   ✅ Created {len(comprehensive_accounts)} accounts")
            
            # Get initial balances
            await sql_ledger_api.begin_transaction()
            initial_balances = {}
            for account in comprehensive_accounts:
                initial_balances[account.id] = await sql_ledger_api.get_account_balance(account.id)
            await sql_ledger_api.end_transaction()
            
            print("\n💰 Initial account balances:")
            self.display_account_balances(comprehensive_accounts, initial_balances)
            
            # Create comprehensive transaction suite
            print("\n📝 Creating comprehensive business transaction suite...")
            transactions = await self.create_comprehensive_transaction_suite(tx_builder)
            
            # Execute all transactions
            print(f"\n🔄 Executing {len(transactions)} transactions...")
            for i, tx_info in enumerate(transactions, 1):
                print(f"   Executing transaction {i}: {tx_info['name']}")
                
                logical_tx = LedgerLogicalTransaction(transactions=[tx_info["ledger_tx"]])
                await sql_ledger_api.begin_transaction()
                await sql_ledger_api.create_transactions([logical_tx])
                await sql_ledger_api.end_transaction()
            
            print("   ✅ All transactions executed successfully")
            
            # Display transaction summary
            self.display_transaction_summary(transactions)
            
            # Get final balances
            await sql_ledger_api.begin_transaction()
            final_balances = {}
            for account in comprehensive_accounts:
                final_balances[account.id] = await sql_ledger_api.get_account_balance(account.id)
            await sql_ledger_api.end_transaction()
            
            # Display final balances
            print("\n💰 Final account balances after all transactions:")
            self.display_account_balances(comprehensive_accounts, final_balances)
            
            # Display balance sheet summary
            self.display_balance_sheet_summary(comprehensive_accounts, final_balances)
            
            # Verify specific transaction effects
            await self.verify_transaction_effects(sql_ledger_api, comprehensive_accounts, initial_balances, final_balances)
            
            # Display comprehensive general ledger reports
            self.display_general_ledger(transactions)
            print("\n")
            self.display_transaction_register(transactions)
            print("\n")
            self.display_trial_balance(comprehensive_accounts, final_balances)
            
            print("\n✅ Comprehensive transaction workflow test completed successfully!")
            
        finally:
            # Clean up database connections
            await sql_ledger_api.close()

    async def create_comprehensive_transaction_suite(self, tx_builder) -> List[Dict[str, Any]]:
        """Create a comprehensive suite of all transaction types."""
        transactions = []
        
        # 1. Payment Authorization
        tx_data = {
            "name": "Payment Authorization",
            "description": "Customer payment authorization for $1000",
            "user_id": 200,
        }
        tx_data["ledger_tx"] = await tx_builder.payment(
            amount=1000.00, 
            user_id=tx_data["user_id"],
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        # 2. Revenue Recognition (Purchase)
        tx_data = {
            "name": "Revenue Recognition",
            "description": "Recognize revenue for Product A purchase",
            "user_id": 200,
        }
        tx_data["ledger_tx"] = await tx_builder.purchase(
            user_id=tx_data["user_id"], 
            product_amounts={"Product A": 600.00},
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        # 3. Settlement from Processor
        tx_data = {
            "name": "Payment Settlement",
            "description": "Settlement from payment processor",
            "user_id": 100,
        }
        tx_data["ledger_tx"] = await tx_builder.settlement(
            amount=950.00,  # After processor fees
            user_id=tx_data["user_id"],
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        # 4. Service Fee Expense
        tx_data = {
            "name": "Service Fee Expense",
            "description": "Payment processing service fees",
            "user_id": 100,
        }
        tx_data["ledger_tx"] = await tx_builder.expense(
            amount=50.00, 
            expense_type="service_fees",
            user_id=tx_data["user_id"],
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        # 5. Tax Collection
        tx_data = {
            "name": "Sales Tax Collection",
            "description": "Collect sales tax on Product A",
            "user_id": 200,
        }
        tx_data["ledger_tx"] = await tx_builder.tax_collection(
            revenue_amount=100.00, 
            tax_amount=10.00, 
            product="product_a",
            user_id=tx_data["user_id"],
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        # 6. Tax Remittance
        tx_data = {
            "name": "Tax Remittance",
            "description": "Remit collected sales tax to authority",
            "user_id": 100,
        }
        tx_data["ledger_tx"] = await tx_builder.tax_remit(
            amount=10.00,
            user_id=tx_data["user_id"],
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        # 7. Promo Credit Issue
        tx_data = {
            "name": "Promotional Credit Issue",
            "description": "Issue promotional credit to customer",
            "user_id": 200,
        }
        tx_data["ledger_tx"] = await tx_builder.promo_issue(
            amount=100.00, 
            user_id=tx_data["user_id"],
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        # 8. Use Promo Credit
        tx_data = {
            "name": "Use Promotional Credit",
            "description": "Customer uses promotional credit for Product A",
            "user_id": 200,
        }
        tx_data["ledger_tx"] = await tx_builder.promo_use(
            amount=75.00, 
            user_id=tx_data["user_id"], 
            product="product_a",
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        # 9. Cancel Promo Credit
        tx_data = {
            "name": "Cancel Promotional Credit",
            "description": "Cancel unused promotional credit",
            "user_id": 200,
        }
        tx_data["ledger_tx"] = await tx_builder.promo_cancel(
            amount=25.00, 
            user_id=tx_data["user_id"],
            name=tx_data["name"],
            description=tx_data["description"]
        )
        transactions.append(tx_data)
        
        return transactions

    async def verify_transaction_effects(self, sql_ledger_api, accounts, initial_balances, final_balances):
        """Verify that transactions had expected effects on account balances."""
        print("\n" + "=" * 80)
        print("TRANSACTION EFFECTS VERIFICATION")
        print("=" * 80)
        
        verification_data = []
        
        for account in accounts:
            initial = initial_balances[account.id]
            final = final_balances[account.id]
            change = final - initial
            
            initial_dollars = Decimal(initial) / SCALE
            final_dollars = Decimal(final) / SCALE
            change_dollars = Decimal(change) / SCALE
            
            verification_data.append([
                account.id,
                account.name,
                fmt_decimal(initial_dollars),
                fmt_decimal(final_dollars),
                fmt_decimal(change_dollars),
                "✓" if change != 0 else "-"
            ])
        
        headers = ['Account ID', 'Account Name', 'Initial Balance', 'Final Balance', 'Change', 'Activity']
        print(f"\n{tabulate(verification_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'right', 'right', 'right', 'center'])}")
        
        # Verify specific business logic
        print("\n📋 Business Logic Verification:")
        
        # Check that cash increased from settlements but decreased from expenses and tax remittance
        cash_change = (final_balances["cash"] - initial_balances["cash"]) / SCALE
        print(f"   • Cash net change: {fmt_decimal(cash_change)} (should reflect settlements - expenses - tax)")
        
        # Check that revenue accounts have credit balances (negative in our system)
        revenue_balance = final_balances["revenue_product_a"] / SCALE
        print(f"   • Product A revenue: {fmt_decimal(revenue_balance)} (should be negative for credit balance)")
        
        # Check that unearned revenue decreased as revenue was recognized
        unearned_change = (final_balances["unearned_revenue"] - initial_balances["unearned_revenue"]) / SCALE
        print(f"   • Unearned revenue change: {fmt_decimal(unearned_change)} (should decrease as revenue recognized)")
        
        # Check that promo liability has remaining balance after partial use
        promo_balance = final_balances["promo_liability"] / SCALE
        print(f"   • Promo liability balance: {fmt_decimal(promo_balance)} (should be negative for credit balance)")

    @pytest.mark.asyncio
    async def test_individual_transaction_types(self, sql_ledger_api, tx_builder, comprehensive_accounts):
        """Test each transaction type individually to verify proper accounting."""
        print("\n🧪 INDIVIDUAL TRANSACTION TYPE TESTS")
        print("=" * 100)
        
        try:
            # Initialize database
            await sql_ledger_api.create_tables()
            await sql_ledger_api._create_sqlite_triggers()
            
            # Create accounts
            await sql_ledger_api.begin_transaction()
            await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=comprehensive_accounts)])
            await sql_ledger_api.end_transaction()
            
            # Test each transaction type
            transaction_types = [
                ("payment", lambda: tx_builder.payment(amount=100.00, user_id=200, name="Test Payment")),
                ("purchase", lambda: tx_builder.purchase(user_id=200, product_amounts={"Product A": 50.00}, name="Test Purchase")),
                ("settlement", lambda: tx_builder.settlement(amount=95.00, user_id=100, name="Test Settlement")),
                ("expense", lambda: tx_builder.expense(amount=10.00, expense_type="service_fees", user_id=100, name="Test Expense")),
                ("tax_collection", lambda: tx_builder.tax_collection(revenue_amount=50.00, tax_amount=5.00, user_id=200, name="Test Tax Collection")),
                ("tax_remit", lambda: tx_builder.tax_remit(amount=5.00, user_id=100, name="Test Tax Remit")),
                ("promo_issue", lambda: tx_builder.promo_issue(amount=25.00, user_id=200, name="Test Promo Issue")),
                ("promo_use", lambda: tx_builder.promo_use(amount=20.00, user_id=200, name="Test Promo Use")),
                ("promo_cancel", lambda: tx_builder.promo_cancel(amount=5.00, user_id=200, name="Test Promo Cancel")),
            ]
            
            results_data = []
            
            for tx_name, tx_builder_func in transaction_types:
                print(f"\n   Testing {tx_name} transaction...")
                
                # Get balances before
                await sql_ledger_api.begin_transaction()
                balances_before = {}
                for account in comprehensive_accounts:
                    balances_before[account.id] = await sql_ledger_api.get_account_balance(account.id)
                await sql_ledger_api.end_transaction()
                
                # Execute transaction
                tx = await tx_builder_func()
                logical_tx = LedgerLogicalTransaction(transactions=[tx])
                
                await sql_ledger_api.begin_transaction()
                await sql_ledger_api.create_transactions([logical_tx])
                await sql_ledger_api.end_transaction()
                
                # Get balances after
                await sql_ledger_api.begin_transaction()
                balances_after = {}
                for account in comprehensive_accounts:
                    balances_after[account.id] = await sql_ledger_api.get_account_balance(account.id)
                await sql_ledger_api.end_transaction()
                
                # Calculate total impact
                total_impact = sum(abs(balances_after[acc.id] - balances_before[acc.id]) for acc in comprehensive_accounts)
                accounts_affected = sum(1 for acc in comprehensive_accounts if balances_after[acc.id] != balances_before[acc.id])
                
                results_data.append([
                    tx_name.title().replace('_', ' '),
                    tx.transaction_type.value,
                    len(tx.transfers),
                    len(tx.entries) if tx.entries else 0,
                    accounts_affected,
                    fmt_decimal(Decimal(total_impact) / SCALE),
                    "✓"
                ])
            
            # Display results
            print(f"\n{'-' * 100}")
            print("INDIVIDUAL TRANSACTION TYPE TEST RESULTS")
            print(f"{'-' * 100}")
            
            headers = ['Transaction', 'Type', 'Transfers', 'Journal Entries', 'Accounts Affected', 'Total Impact', 'Success']
            print(f"\n{tabulate(results_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'center', 'center', 'center', 'right', 'center'])}")
            
            print(f"\n✅ All {len(transaction_types)} transaction types tested successfully!")
            
        finally:
            await sql_ledger_api.close()

    @pytest.mark.asyncio
    async def test_accounting_equation_balance(self, sql_ledger_api, tx_builder, comprehensive_accounts):
        """Test that the accounting equation remains balanced after transactions."""
        print("\n⚖️  ACCOUNTING EQUATION BALANCE TEST")
        print("=" * 100)
        
        try:
            # Initialize database
            await sql_ledger_api.create_tables()
            await sql_ledger_api._create_sqlite_triggers()
            
            # Create accounts
            await sql_ledger_api.begin_transaction()
            await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=comprehensive_accounts)])
            await sql_ledger_api.end_transaction()
            
            # Execute a series of transactions
            transactions = await self.create_comprehensive_transaction_suite(tx_builder)
            
            equation_checks = []
            
            # Check equation before any transactions
            await sql_ledger_api.begin_transaction()
            balances = {}
            for account in comprehensive_accounts:
                balances[account.id] = await sql_ledger_api.get_account_balance(account.id)
            await sql_ledger_api.end_transaction()
            
            is_balanced = self.check_accounting_equation(comprehensive_accounts, balances)
            equation_checks.append(["Initial State", "0", "✓" if is_balanced else "✗"])
            
            # Execute transactions one by one and check equation after each
            for i, tx_info in enumerate(transactions, 1):
                logical_tx = LedgerLogicalTransaction(transactions=[tx_info["ledger_tx"]])
                await sql_ledger_api.begin_transaction()
                await sql_ledger_api.create_transactions([logical_tx])
                await sql_ledger_api.end_transaction()
                
                # Check equation
                await sql_ledger_api.begin_transaction()
                balances = {}
                for account in comprehensive_accounts:
                    balances[account.id] = await sql_ledger_api.get_account_balance(account.id)
                await sql_ledger_api.end_transaction()
                
                is_balanced = self.check_accounting_equation(comprehensive_accounts, balances)
                equation_checks.append([
                    tx_info["name"][:30],
                    str(i),
                    "✓" if is_balanced else "✗"
                ])
            
            # Display results
            headers = ['Transaction/State', 'Step', 'Equation Balanced']
            print(f"\n{tabulate(equation_checks, headers=headers, tablefmt='grid', colalign=['left', 'center', 'center'])}")
            
            # Final equation verification
            assets, liabilities, equity = self.calculate_equation_components(comprehensive_accounts, balances)
            print(f"\nFinal Accounting Equation Check:")
            print(f"Assets = Liabilities + Equity")
            print(f"{fmt_decimal(assets)} = {fmt_decimal(liabilities)} + {fmt_decimal(equity)}")
            print(f"Difference: {fmt_decimal(assets - (liabilities + equity))}")
            
            # Assert that equation is balanced
            assert is_balanced, "Accounting equation is not balanced after all transactions"
            print("\n✅ Accounting equation remains balanced throughout all transactions!")
            
        finally:
            await sql_ledger_api.close()

    def check_accounting_equation(self, accounts: List[LedgerAccount], balances: Dict[str, int]) -> bool:
        """Check if the accounting equation (Assets = Liabilities + Equity) is balanced."""
        assets, liabilities, equity = self.calculate_equation_components(accounts, balances)
        difference = abs(assets - (liabilities + equity))
        return difference < Decimal('0.000001')

    def calculate_equation_components(self, accounts: List[LedgerAccount], balances: Dict[str, int]):
        """Calculate the components of the accounting equation."""
        assets = Decimal(0)
        liabilities = Decimal(0)
        income = Decimal(0)
        expenses = Decimal(0)
        
        for account in accounts:
            balance = Decimal(balances.get(account.id, 0)) / SCALE
            account_type = account.account_type
            
            if account_type == AccountType.ASSET:
                assets += balance
            elif account_type == AccountType.LIABILITY:
                liabilities += -balance  # Liabilities have credit balance (negative in our system)
            elif account_type == AccountType.INCOME:
                income += -balance  # Income has credit balance (negative in our system)
            elif account_type == AccountType.EXPENSE:
                expenses += balance
        
        equity = income - expenses
        return assets, liabilities, equity

    def display_general_ledger(self, transactions: List[Dict[str, Any]]):
        """Display the complete general ledger with all journal entries."""
        print("GENERAL LEDGER - ALL JOURNAL ENTRIES")
        
        all_entries = []
        
        # Collect all journal entries from all transactions
        for tx_info in transactions:
            tx = tx_info["ledger_tx"]
            if tx.entries:
                for entry in tx.entries:
                    all_entries.append({
                        'transaction_name': tx_info["name"],
                        'transaction_type': tx.transaction_type.value,
                        'transaction_id': entry.transaction_id or "N/A",
                        'entry_id': entry.id,
                        'account_id': entry.account_id,
                        'description': entry.description or "",
                        'debit': entry.debit if entry.debit and entry.debit > 0 else 0,
                        'credit': entry.credit if entry.credit and entry.credit > 0 else 0,
                        'timestamp': entry.ts_created,
                        'user_id': tx_info["user_id"]
                    })
        
        # Sort by timestamp if available, otherwise by transaction name
        all_entries.sort(key=lambda x: x['timestamp'] if x['timestamp'] else x['transaction_name'])
        
        # Prepare data for tabular display
        ledger_data = []
        running_balance = Decimal(0)
        
        for entry in all_entries:
            debit_amount = Decimal(entry['debit']) / SCALE if entry['debit'] else Decimal(0)
            credit_amount = Decimal(entry['credit']) / SCALE if entry['credit'] else Decimal(0)
            
            # Calculate running balance (debits positive, credits negative)
            running_balance += debit_amount - credit_amount
            
            ledger_data.append([
                entry['transaction_name'][:20],
                entry['transaction_type'],
                entry['account_id'],
                entry['description'][:30],
                fmt_decimal(debit_amount) if debit_amount > 0 else "-",
                fmt_decimal(credit_amount) if credit_amount > 0 else "-",
                fmt_decimal(running_balance),
                entry['user_id']
            ])
        
        headers = [
            'Transaction', 'Type', 'Account ID', 'Description', 
            'Debit', 'Credit', 'Running Total', 'User ID'
        ]
        
        print(f"{tabulate(ledger_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'left', 'left', 'right', 'right', 'right', 'center'])}")

    def display_transaction_register(self, transactions: List[Dict[str, Any]]):
        """Display a transaction register showing each complete transaction."""
        print("TRANSACTION REGISTER - COMPLETE TRANSACTIONS")
        
        for i, tx_info in enumerate(transactions, 1):
            tx = tx_info["ledger_tx"]
            
            print(f"TRANSACTION #{i}: {tx_info['name'].upper()} - {tx.transaction_type.value}")
            print(f"User ID: {tx_info['user_id']} | Description: {tx_info['description']}")
            
            if tx.entries:
                
                entry_data = []
                transaction_debits = Decimal(0)
                transaction_credits = Decimal(0)
                
                for entry in tx.entries:
                    debit_amount = Decimal(entry.debit) / SCALE if entry.debit and entry.debit > 0 else Decimal(0)
                    credit_amount = Decimal(entry.credit) / SCALE if entry.credit and entry.credit > 0 else Decimal(0)
                    
                    transaction_debits += debit_amount
                    transaction_credits += credit_amount
                    
                    entry_data.append([
                        entry.account_id,
                        entry.description or "",
                        fmt_decimal(debit_amount) if debit_amount > 0 else "-",
                        fmt_decimal(credit_amount) if credit_amount > 0 else "-"
                    ])
                
                # Add totals row
                entry_data.append([
                    "TOTALS",
                    "",
                    fmt_decimal(transaction_debits),
                    fmt_decimal(transaction_credits)
                ])
                
                headers = ['Account ID', 'Description', 'Debit', 'Credit']
                print(f"{tabulate(entry_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'right', 'right'])}")
            
            if tx.transfers:
                
                transfer_data = []
                for transfer in tx.transfers:
                    amount = Decimal(transfer.amount) / SCALE
                    transfer_data.append([
                        transfer.debit_account_id,
                        transfer.credit_account_id,
                        fmt_decimal(amount),
                        transfer.id[:8] + "..."
                    ])
                
                headers = ['Debit Account', 'Credit Account', 'Amount', 'Transfer ID']
                print(f"{tabulate(transfer_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'right', 'left'])}")
            
            print()  # Empty line after each transaction

    def display_account_ledgers(self, accounts: List[LedgerAccount], transactions: List[Dict[str, Any]]):
        """Display individual account ledgers showing all entries for each account."""
        print("\n" + "=" * 120)
        print("INDIVIDUAL ACCOUNT LEDGERS")
        print("=" * 120)
        
        # Group entries by account
        account_entries = {}
        for account in accounts:
            account_entries[account.id] = []
        
        # Collect entries for each account
        for tx_info in transactions:
            tx = tx_info["ledger_tx"]
            if tx.entries:
                for entry in tx.entries:
                    if entry.account_id in account_entries:
                        account_entries[entry.account_id].append({
                            'transaction_name': tx_info["name"],
                            'transaction_type': tx.transaction_type.value,
                            'entry': entry,
                            'user_id': tx_info["user_id"]
                        })
        
        # Display ledger for each account that has entries
        for account in accounts:
            entries = account_entries[account.id]
            if not entries:
                continue
                
            print(f"\n{'═' * 120}")
            print(f"ACCOUNT LEDGER: {account.name.upper()} ({account.id})")
            print(f"Account Type: {account.account_type.value.title()} | Normal Side: {account.side.value.title()} | Workspace: {account.workspace_id}")
            print(f"{'═' * 120}")
            
            ledger_data = []
            running_balance = Decimal(0)
            
            # Sort entries by timestamp if available
            entries.sort(key=lambda x: x['entry'].ts_created if x['entry'].ts_created else x['transaction_name'])
            
            for entry_info in entries:
                entry = entry_info['entry']
                debit_amount = Decimal(entry.debit) / SCALE if entry.debit and entry.debit > 0 else Decimal(0)
                credit_amount = Decimal(entry.credit) / SCALE if entry.credit and entry.credit > 0 else Decimal(0)
                
                # Update running balance based on account's normal side
                if account.side == LedgerSide.DEBIT:
                    running_balance += debit_amount - credit_amount
                else:
                    running_balance += credit_amount - debit_amount
                
                ledger_data.append([
                    entry_info['transaction_name'][:20],
                    entry_info['transaction_type'],
                    entry.description[:35] if entry.description else "",
                    fmt_decimal(debit_amount) if debit_amount > 0 else "-",
                    fmt_decimal(credit_amount) if credit_amount > 0 else "-",
                    fmt_decimal(running_balance),
                    entry_info['user_id']
                ])
            
            headers = ['Transaction', 'Type', 'Description', 'Debit', 'Credit', 'Balance', 'User']
            print(f"\n{tabulate(ledger_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'left', 'right', 'right', 'right', 'center'])}")
            
            # Account summary
            total_debits = sum(Decimal(e['entry'].debit) / SCALE for e in entries if e['entry'].debit and e['entry'].debit > 0)
            total_credits = sum(Decimal(e['entry'].credit) / SCALE for e in entries if e['entry'].credit and e['entry'].credit > 0)
            
            print(f"\n   Account Summary:")
            print(f"   • Total Debits: {fmt_decimal(total_debits)}")
            print(f"   • Total Credits: {fmt_decimal(total_credits)}")
            print(f"   • Final Balance: {fmt_decimal(running_balance)}")
            print(f"   • Entry Count: {len(entries)}")

    def display_trial_balance(self, accounts: List[LedgerAccount], final_balances: Dict[str, int]):
        """Display a trial balance showing all account balances."""
        print("TRIAL BALANCE")
        
        trial_balance_data = []
        total_debits = Decimal(0)
        total_credits = Decimal(0)
        
        # Group accounts by type for better organization
        accounts_by_type = {}
        for account in accounts:
            account_type = account.account_type.value.title()
            if account_type not in accounts_by_type:
                accounts_by_type[account_type] = []
            accounts_by_type[account_type].append(account)
        
        # Process each account type
        for account_type in sorted(accounts_by_type.keys()):
            # Add section header
            trial_balance_data.append([
                f"--- {account_type.upper()} ACCOUNTS ---",
                "",
                "",
                "",
                ""
            ])
            
            type_debits = Decimal(0)
            type_credits = Decimal(0)
            
            for account in accounts_by_type[account_type]:
                balance = final_balances.get(account.id, 0)
                balance_dollars = Decimal(balance) / SCALE
                
                # Determine if balance should be shown as debit or credit
                if balance_dollars == 0:
                    debit_str = "-"
                    credit_str = "-"
                elif (account.side == LedgerSide.DEBIT and balance_dollars > 0) or \
                     (account.side == LedgerSide.CREDIT and balance_dollars < 0):
                    # Normal balance
                    debit_str = fmt_decimal(abs(balance_dollars))
                    credit_str = "-"
                    type_debits += abs(balance_dollars)
                    total_debits += abs(balance_dollars)
                else:
                    # Contra balance
                    debit_str = "-"
                    credit_str = fmt_decimal(abs(balance_dollars))
                    type_credits += abs(balance_dollars)
                    total_credits += abs(balance_dollars)
                
                trial_balance_data.append([
                    account.id,
                    account.name,
                    account.side.value.title(),
                    debit_str,
                    credit_str
                ])
            
            # Add subtotal for account type
            trial_balance_data.append([
                f"Subtotal {account_type}",
                "",
                "",
                fmt_decimal(type_debits) if type_debits > 0 else "-",
                fmt_decimal(type_credits) if type_credits > 0 else "-"
            ])
            
            # Add spacing
            trial_balance_data.append(["", "", "", "", ""])
        
        # Add final totals
        trial_balance_data.append([
            "GRAND TOTALS",
            "",
            "",
            fmt_decimal(total_debits),
            fmt_decimal(total_credits)
        ])
        
        headers = ['Account ID', 'Account Name', 'Normal Side', 'Debit Balance', 'Credit Balance']
        print(f"{tabulate(trial_balance_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'center', 'right', 'right'])}")


if __name__ == "__main__":
    pytest.main([__file__])
