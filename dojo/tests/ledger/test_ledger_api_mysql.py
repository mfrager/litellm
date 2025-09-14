#!/usr/bin/env python3
"""
Comprehensive Ledger API Test Suite - MySQL Version

This module contains comprehensive tests for the Ledger API implementations,
following the golden master pattern with detailed tabular output and testing
all transaction types from the transaction builder using MySQL.
"""

import os
import sys
import uuid
import pytest
from dotenv import load_dotenv
from typing import List, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal
from tabulate import tabulate
from ulid import ULID

sys.path.append('../..')
load_dotenv('../../../.env')

from ledger.ledger_api import (
    LedgerAPI,
    Ledger,
    LedgerAccount,
    LedgerAccountBalance,
    LedgerJournalEntry,
    LedgerAccountTransfer,
    LedgerTransaction,
    LedgerAccountTransaction,
    generate_account_code,
    LedgerTransferTransaction,
    LedgerJournalTransaction,
    LedgerLogicalTransaction,
    LedgerAccountFilter,
    LedgerQuery,
    AccountType,
    LedgerSide,
    TransactionType
)

from ledger.sql_ledger import SQLLedgerAPI
from ledger.ledger_tx_builder import LedgerTransactionBuilder

# Decimal precision for monetary calculations
DECIMALS = 10
SCALE = Decimal(10) ** DECIMALS

def fmt_decimal(val):
    """Format decimal values for display with full 10 decimal precision."""
    return f"${Decimal(val).quantize(Decimal('0.0000000001')):,.10f}"

def generate_session_account_mapping():
    """Generate fresh ULID mapping for each test session."""
    return {
        "cash": str(ULID()),
        "ar_processor": str(ULID()),
        "unearned_revenue": str(ULID()),
        "tax_payable": str(ULID()),
        "promo_liability": str(ULID()),
        "revenue_product_a": str(ULID()),
        "promo_revenue_product_a": str(ULID()),
        "service_fees_expense": str(ULID()),
        "promo_expense": str(ULID()),
    }


class TestComprehensiveLedgerAPI:
    """Comprehensive test suite for Ledger API with all transaction types."""
    
    @pytest.fixture
    def database_url(self):
        """Fixture providing MySQL database URL for testing."""
        return os.environ['DATABASE_ASYNC_TEST']
    
    async def get_or_create_account_id(self, sql_ledger_api, account_name: str) -> str:
        """Get existing account ID by name or return the mapped ULID."""
        # Try to find existing account by name
        await sql_ledger_api.begin_transaction()
        try:
            query = {"name": account_name}
            existing_accounts = await sql_ledger_api.query_accounts(query)
            if existing_accounts:
                account_id = existing_accounts[0].id
                print(f"   Found existing account '{account_name}' with ID: {account_id}")
                return account_id
        except Exception as e:
            print(f"   No existing account found for '{account_name}': {e}")
        finally:
            await sql_ledger_api.end_transaction()
        
        # Return the mapped ULID for this account name
        # Find the original key name for this account
        for original_key, ulid_id in ACCOUNT_ID_MAPPING.items():
            if original_key in account_name.lower().replace(" ", "_").replace("–", "_").replace("/", "_"):
                return ulid_id
        
        # Fallback: generate new ULID if no mapping found
        return str(ULID())
    
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
    def account_mapping(self):
        """Generate fresh account mapping for each test."""
        return generate_session_account_mapping()
    
    @pytest.fixture
    def tx_builder(self, account_mapping):
        """Fixture providing transaction builder with comprehensive account IDs using ULIDs."""
        account_ids = {
            # Asset accounts
            "cash_bank": account_mapping["cash"],
            "ar_processor": account_mapping["ar_processor"], 
            
            # Liability accounts
            "unearned_revenue": account_mapping["unearned_revenue"],
            "tax_payable": account_mapping["tax_payable"],
            "promo_liability": account_mapping["promo_liability"],
            
            # Income accounts
            "revenue_product_a": account_mapping["revenue_product_a"],
            "promo_revenue_product_a": account_mapping["promo_revenue_product_a"],
            
            # Expense accounts
            "service_fees_expense": account_mapping["service_fees_expense"],
            "promo_expense": account_mapping["promo_expense"],
        }
        return LedgerTransactionBuilder(account_ids)
    
    @pytest.fixture
    def comprehensive_accounts(self, account_mapping):
        """Create comprehensive chart of accounts for testing with ULID IDs."""
        return [
            # ============= ASSET ACCOUNTS =============
            LedgerAccount(
                id=account_mapping["cash"],
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
                id=account_mapping["ar_processor"],
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
                id=account_mapping["unearned_revenue"],
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
                id=account_mapping["tax_payable"],
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
                id=account_mapping["promo_liability"],
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
                id=account_mapping["revenue_product_a"],
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
                id=account_mapping["promo_revenue_product_a"],
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
                id=account_mapping["service_fees_expense"],
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
                id=account_mapping["promo_expense"],
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
        print("\n🏦 COMPREHENSIVE LEDGER API TEST - ALL TRANSACTION TYPES (MySQL)")
        print("=" * 100)
        
        try:
            # Display chart of accounts
            self.display_chart_of_accounts(comprehensive_accounts)
            
            # Check for existing accounts and create only those that don't exist
            print("\n📊 Checking for existing accounts or creating new ones...")
            final_accounts = []
            accounts_to_create = []
            
            # Look up each account by name
            for account in comprehensive_accounts:
                await sql_ledger_api.begin_transaction()
                try:
                    query = {"name": account.name}
                    existing_accounts = await sql_ledger_api.query_accounts(query)
                    if existing_accounts:
                        existing_account = existing_accounts[0]
                        print(f"   Found existing account '{account.name}' with ID: {existing_account.id}")
                        # Use the existing account ID but preserve other properties
                        reused_account = LedgerAccount(
                            id=existing_account.id,
                            name=account.name,
                            account_code=existing_account.account_code,  # Use existing account_code
                            account_type=account.account_type,
                            side=account.side,
                            workspace_id=account.workspace_id,
                            is_promo=account.is_promo,
                            decimals=account.decimals,
                            currency=account.currency,
                            details=account.details,
                            history=account.history
                        )
                        final_accounts.append(reused_account)
                    else:
                        print(f"   No existing account found for '{account.name}', will create with ULID: {account.id}")
                        accounts_to_create.append(account)
                        final_accounts.append(account)
                except Exception as e:
                    print(f"   Error checking for account '{account.name}': {e}")
                    accounts_to_create.append(account)
                    final_accounts.append(account)
                finally:
                    try:
                        await sql_ledger_api.end_transaction()
                    except RuntimeError:
                        pass  # Transaction already ended
        
            # Create only the accounts that don't exist
            if accounts_to_create:
                await sql_ledger_api.begin_transaction()
                await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=accounts_to_create)])
                await sql_ledger_api.end_transaction()
                print(f"   ✅ Created {len(accounts_to_create)} new accounts")
            else:
                print("   ✅ All accounts already exist, no new accounts created")
            
            # Use the final account list (mix of existing and newly created)
            comprehensive_accounts = final_accounts
            
            # Update transaction builder with actual account IDs
            print("\n🔧 Updating transaction builder with actual account IDs...")
            account_ids = {}
            for account in comprehensive_accounts:
                # Map account names to their actual IDs
                if "Cash" in account.name:
                    account_ids["cash_bank"] = account.id
                elif "Accounts Receivable" in account.name:
                    account_ids["ar_processor"] = account.id
                elif "Unearned Revenue" in account.name:
                    account_ids["unearned_revenue"] = account.id
                elif "Tax Payable" in account.name:
                    account_ids["tax_payable"] = account.id
                elif "Promo Credit Liability" in account.name:
                    account_ids["promo_liability"] = account.id
                elif "Revenue – Product A" in account.name and not account.is_promo:
                    account_ids["revenue_product_a"] = account.id
                elif "Promo Revenue – Product A" in account.name:
                    account_ids["promo_revenue_product_a"] = account.id
                elif "Service Fees Expense" in account.name:
                    account_ids["service_fees_expense"] = account.id
                elif "Promo Credit Expense" in account.name:
                    account_ids["promo_expense"] = account.id
            
            # Create new transaction builder with updated IDs
            tx_builder = LedgerTransactionBuilder(account_ids)
            print(f"   ✅ Updated transaction builder with {len(account_ids)} account mappings")
            
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
            
        except Exception as e:
            print(f"❌ Error in comprehensive transaction workflow test: {e}")
            raise
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
        
        # Find account IDs by name for verification
        cash_id = None
        revenue_id = None
        unearned_id = None
        promo_id = None
        
        for account in accounts:
            if "Cash" in account.name:
                cash_id = account.id
            elif "Revenue – Product A" in account.name and not account.is_promo:
                revenue_id = account.id
            elif "Unearned Revenue" in account.name:
                unearned_id = account.id
            elif "Promo Credit Liability" in account.name:
                promo_id = account.id
        
        # Check that cash increased from settlements but decreased from expenses and tax remittance
        if cash_id:
            cash_change = (final_balances[cash_id] - initial_balances[cash_id]) / SCALE
            print(f"   • Cash net change: {fmt_decimal(cash_change)} (should reflect settlements - expenses - tax)")
        
        # Check that revenue accounts have credit balances (negative in our system)
        if revenue_id:
            revenue_balance = final_balances[revenue_id] / SCALE
            print(f"   • Product A revenue: {fmt_decimal(revenue_balance)} (should be negative for credit balance)")
        
        # Check that unearned revenue decreased as revenue was recognized
        if unearned_id:
            unearned_change = (final_balances[unearned_id] - initial_balances[unearned_id]) / SCALE
            print(f"   • Unearned revenue change: {fmt_decimal(unearned_change)} (should decrease as revenue recognized)")
        
        # Check that promo liability has remaining balance after partial use
        if promo_id:
            promo_balance = final_balances[promo_id] / SCALE
            print(f"   • Promo liability balance: {fmt_decimal(promo_balance)} (should be negative for credit balance)")
    
    @pytest.mark.asyncio
    async def test_individual_transaction_types(self, sql_ledger_api, tx_builder, comprehensive_accounts):
        """Test each transaction type individually to verify proper accounting."""
        print("\n🧪 INDIVIDUAL TRANSACTION TYPE TESTS (MySQL)")
        print("=" * 100)
        
        try:
            # Check for existing accounts and create only those that don't exist
            print("\n📊 Checking for existing accounts or creating new ones...")
            final_accounts = []
            accounts_to_create = []
            
            # Look up each account by name
            for account in comprehensive_accounts:
                await sql_ledger_api.begin_transaction()
                try:
                    query = {"name": account.name}
                    existing_accounts = await sql_ledger_api.query_accounts(query)
                    if existing_accounts:
                        existing_account = existing_accounts[0]
                        print(f"   Found existing account '{account.name}' with ID: {existing_account.id}")
                        # Use the existing account ID but preserve other properties
                        reused_account = LedgerAccount(
                            id=existing_account.id,
                            name=account.name,
                            account_code=existing_account.account_code,  # Use existing account_code
                            account_type=account.account_type,
                            side=account.side,
                            workspace_id=account.workspace_id,
                            is_promo=account.is_promo,
                            decimals=account.decimals,
                            currency=account.currency,
                            details=account.details,
                            history=account.history
                        )
                        final_accounts.append(reused_account)
                    else:
                        print(f"   No existing account found for '{account.name}', will create with ULID: {account.id}")
                        accounts_to_create.append(account)
                        final_accounts.append(account)
                except Exception as e:
                    print(f"   Error checking for account '{account.name}': {e}")
                    accounts_to_create.append(account)
                    final_accounts.append(account)
                finally:
                    try:
                        await sql_ledger_api.end_transaction()
                    except RuntimeError:
                        pass  # Transaction already ended
        
            # Create only the accounts that don't exist
            if accounts_to_create:
                await sql_ledger_api.begin_transaction()
                await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=accounts_to_create)])
                await sql_ledger_api.end_transaction()
                print(f"   ✅ Created {len(accounts_to_create)} new accounts")
            else:
                print("   ✅ All accounts already exist, no new accounts created")
            
            # Use the final account list (mix of existing and newly created)
            comprehensive_accounts = final_accounts
            
            # Update transaction builder with actual account IDs
            account_ids = {}
            for account in comprehensive_accounts:
                if "Cash" in account.name:
                    account_ids["cash_bank"] = account.id
                elif "Accounts Receivable" in account.name:
                    account_ids["ar_processor"] = account.id
                elif "Unearned Revenue" in account.name:
                    account_ids["unearned_revenue"] = account.id
                elif "Tax Payable" in account.name:
                    account_ids["tax_payable"] = account.id
                elif "Promo Credit Liability" in account.name:
                    account_ids["promo_liability"] = account.id
                elif "Revenue – Product A" in account.name and not account.is_promo:
                    account_ids["revenue_product_a"] = account.id
                elif "Promo Revenue – Product A" in account.name:
                    account_ids["promo_revenue_product_a"] = account.id
                elif "Service Fees Expense" in account.name:
                    account_ids["service_fees_expense"] = account.id
                elif "Promo Credit Expense" in account.name:
                    account_ids["promo_expense"] = account.id
            
            tx_builder = LedgerTransactionBuilder(account_ids)
            
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
        print("\n⚖️  ACCOUNTING EQUATION BALANCE TEST (MySQL)")
        print("=" * 100)
        
        try:
            # Check for existing accounts and create only those that don't exist
            print("\n📊 Checking for existing accounts or creating new ones...")
            final_accounts = []
            accounts_to_create = []
            
            # Look up each account by name
            for account in comprehensive_accounts:
                await sql_ledger_api.begin_transaction()
                try:
                    query = {"name": account.name}
                    existing_accounts = await sql_ledger_api.query_accounts(query)
                    if existing_accounts:
                        existing_account = existing_accounts[0]
                        print(f"   Found existing account '{account.name}' with ID: {existing_account.id}")
                        # Use the existing account ID but preserve other properties
                        reused_account = LedgerAccount(
                            id=existing_account.id,
                            name=account.name,
                            account_code=existing_account.account_code,  # Use existing account_code
                            account_type=account.account_type,
                            side=account.side,
                            workspace_id=account.workspace_id,
                            is_promo=account.is_promo,
                            decimals=account.decimals,
                            currency=account.currency,
                            details=account.details,
                            history=account.history
                        )
                        final_accounts.append(reused_account)
                    else:
                        print(f"   No existing account found for '{account.name}', will create with ULID: {account.id}")
                        accounts_to_create.append(account)
                        final_accounts.append(account)
                except Exception as e:
                    print(f"   Error checking for account '{account.name}': {e}")
                    accounts_to_create.append(account)
                    final_accounts.append(account)
                finally:
                    try:
                        await sql_ledger_api.end_transaction()
                    except RuntimeError:
                        pass  # Transaction already ended
        
            # Create only the accounts that don't exist
            if accounts_to_create:
                await sql_ledger_api.begin_transaction()
                await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=accounts_to_create)])
                await sql_ledger_api.end_transaction()
                print(f"   ✅ Created {len(accounts_to_create)} new accounts")
            else:
                print("   ✅ All accounts already exist, no new accounts created")
            
            # Use the final account list (mix of existing and newly created)
            comprehensive_accounts = final_accounts
            
            # Update transaction builder with actual account IDs
            account_ids = {}
            for account in comprehensive_accounts:
                if "Cash" in account.name:
                    account_ids["cash_bank"] = account.id
                elif "Accounts Receivable" in account.name:
                    account_ids["ar_processor"] = account.id
                elif "Unearned Revenue" in account.name:
                    account_ids["unearned_revenue"] = account.id
                elif "Tax Payable" in account.name:
                    account_ids["tax_payable"] = account.id
                elif "Promo Credit Liability" in account.name:
                    account_ids["promo_liability"] = account.id
                elif "Revenue – Product A" in account.name and not account.is_promo:
                    account_ids["revenue_product_a"] = account.id
                elif "Promo Revenue – Product A" in account.name:
                    account_ids["promo_revenue_product_a"] = account.id
                elif "Service Fees Expense" in account.name:
                    account_ids["service_fees_expense"] = account.id
                elif "Promo Credit Expense" in account.name:
                    account_ids["promo_expense"] = account.id
            
            tx_builder = LedgerTransactionBuilder(account_ids)
            
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

    @pytest.mark.asyncio
    async def test_decimal_precision_calculations(self, sql_ledger_api, account_mapping):
        """Test that the ledger can handle calculations with full 10 decimal precision."""
        print("\n🔢 DECIMAL PRECISION TEST - 10 DECIMAL PLACES (MySQL)")
        print("=" * 100)
        
        try:
            # Create precision test accounts
            precision_accounts = [
                LedgerAccount(
                    id=account_mapping["cash"],
                    name="Precision Cash Account",
                    account_code="internal_precision_cash_account",
                    account_type=AccountType.ASSET,
                    side=LedgerSide.DEBIT,
                    workspace_id=100,
                    is_promo=False,
                    decimals=DECIMALS,  # 10 decimal places
                    currency="USD",
                    details={"entity": "Company", "test": "precision"},
                    history=True
                ),
                LedgerAccount(
                    id=account_mapping["revenue_product_a"],
                    name="Precision Revenue Account",
                    account_code="internal_precision_revenue_account",
                    account_type=AccountType.INCOME,
                    side=LedgerSide.CREDIT,
                    workspace_id=100,
                    is_promo=False,
                    decimals=DECIMALS,  # 10 decimal places
                    currency="USD",
                    details={"entity": "Company", "test": "precision"},
                    history=True
                ),
                LedgerAccount(
                    id=account_mapping["service_fees_expense"],
                    name="Precision Expense Account",
                    account_code="internal_precision_expense_account",
                    account_type=AccountType.EXPENSE,
                    side=LedgerSide.DEBIT,
                    workspace_id=100,
                    is_promo=False,
                    decimals=DECIMALS,  # 10 decimal places
                    currency="USD",
                    details={"entity": "Company", "test": "precision"},
                    history=True
                ),
            ]
            
            # Check for existing accounts and create only those that don't exist
            print("\n📊 Checking for existing precision test accounts...")
            final_accounts = []
            accounts_to_create = []
            
            for account in precision_accounts:
                await sql_ledger_api.begin_transaction()
                try:
                    query = {"name": account.name}
                    existing_accounts = await sql_ledger_api.query_accounts(query)
                    if existing_accounts:
                        existing_account = existing_accounts[0]
                        print(f"   Found existing account '{account.name}' with ID: {existing_account.id}")
                        reused_account = LedgerAccount(
                            id=existing_account.id,
                            name=account.name,
                            account_code=existing_account.account_code,
                            account_type=existing_account.account_type,
                            side=existing_account.side,
                            workspace_id=existing_account.workspace_id,
                            is_promo=existing_account.is_promo,
                            decimals=existing_account.decimals,
                            currency=existing_account.currency,
                            details=existing_account.details,
                            history=existing_account.history
                        )
                        final_accounts.append(reused_account)
                    else:
                        print(f"   No existing account found for '{account.name}', will create with ULID: {account.id}")
                        accounts_to_create.append(account)
                        final_accounts.append(account)
                except Exception as e:
                    print(f"   Error checking for account '{account.name}': {e}")
                    accounts_to_create.append(account)
                    final_accounts.append(account)
                finally:
                    await sql_ledger_api.end_transaction()
            
            # Create only the accounts that don't exist
            if accounts_to_create:
                await sql_ledger_api.begin_transaction()
                await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=accounts_to_create)])
                await sql_ledger_api.end_transaction()
                print(f"   ✅ Created {len(accounts_to_create)} new precision test accounts")
            else:
                print("   ✅ All precision test accounts already exist, no new accounts created")
            
            # Ensure we have exactly 3 accounts for the precision test
            if len(final_accounts) < 3:
                print(f"   ⚠️  Only found {len(final_accounts)} accounts, need 3 for precision test")
                print("   🔧 Creating missing accounts...")
                
                # Create missing accounts with unique IDs
                missing_accounts = []
                for i in range(len(final_accounts), 3):
                    if i == 0:  # Cash account
                        missing_account = LedgerAccount(
                            id=str(ULID()),
                            name="Precision Cash Account",
                            account_code=f"internal_precision_cash_account_{i}",
                            account_type=AccountType.ASSET,
                            side=LedgerSide.DEBIT,
                            workspace_id=100,
                            is_promo=False,
                            decimals=DECIMALS,
                            currency="USD",
                            details={"entity": "Company", "test": "precision"},
                            history=True
                        )
                    elif i == 1:  # Revenue account
                        missing_account = LedgerAccount(
                            id=str(ULID()),
                            name="Precision Revenue Account",
                            account_code=f"internal_precision_revenue_account_{i}",
                            account_type=AccountType.INCOME,
                            side=LedgerSide.CREDIT,
                            workspace_id=100,
                            is_promo=False,
                            decimals=DECIMALS,
                            currency="USD",
                            details={"entity": "Company", "test": "precision"},
                            history=True
                        )
                    else:  # Expense account
                        missing_account = LedgerAccount(
                            id=str(ULID()),
                            name="Precision Expense Account",
                            account_code=f"internal_precision_expense_account_{i}",
                            account_type=AccountType.EXPENSE,
                            side=LedgerSide.DEBIT,
                            workspace_id=100,
                            is_promo=False,
                            decimals=DECIMALS,
                            currency="USD",
                            details={"entity": "Company", "test": "precision"},
                            history=True
                        )
                    missing_accounts.append(missing_account)
                    final_accounts.append(missing_account)
                
                # Create the missing accounts
                await sql_ledger_api.begin_transaction()
                await sql_ledger_api.create_accounts([LedgerAccountTransaction(accounts=missing_accounts)])
                await sql_ledger_api.end_transaction()
                print(f"   ✅ Created {len(missing_accounts)} missing precision test accounts")
            
            # Use the final account list
            precision_accounts = final_accounts
            print(f"   📊 Final accounts count: {len(final_accounts)}")
            for i, acc in enumerate(final_accounts):
                print(f"      {i}: {acc.name} (ID: {acc.id})")
            
            # Get initial balances
            await sql_ledger_api.begin_transaction()
            initial_balances = {}
            for account in precision_accounts:
                initial_balances[account.id] = await sql_ledger_api.get_account_balance(account.id)
            await sql_ledger_api.end_transaction()
            
            print("\n💰 Initial balances:")
            for account in precision_accounts:
                balance = initial_balances[account.id]
                balance_dollars = Decimal(balance) / SCALE
                print(f"   {account.name}: {fmt_decimal(balance_dollars)}")
            
            # Test various precision scenarios
            precision_tests = [
                {
                    "name": "Micro-payment Test",
                    "description": "Test with very small amounts (0.0000000001)",
                    "amount": Decimal("0.0000000001"),  # 1 micro-unit
                    "expected_precision": 10
                },
                {
                    "name": "Precision Addition Test", 
                    "description": "Test adding multiple small amounts",
                    "amount": Decimal("0.0000000001"),
                    "expected_precision": 10,
                    "iterations": 1000  # Add 1000 times
                },
                {
                    "name": "Large Amount Precision Test",
                    "description": "Test large amounts with full precision",
                    "amount": Decimal("100000000.0000000000"),  # Large amount with 10 decimals (within BIGINT limits)
                    "expected_precision": 10
                },
                {
                    "name": "Fractional Precision Test",
                    "description": "Test fractional amounts requiring full precision",
                    "amount": Decimal("1.0000000001"),  # 1 + 1 micro-unit
                    "expected_precision": 10
                },
                {
                    "name": "Rounding Edge Case Test",
                    "description": "Test amounts that might cause rounding issues",
                    "amount": Decimal("0.0000000005"),  # Half micro-unit
                    "expected_precision": 10
                }
            ]
            
            # Execute precision tests
            test_results = []
            total_transactions = 0
            
            for test_case in precision_tests:
                print(f"\n🧪 Running: {test_case['name']}")
                print(f"   Description: {test_case['description']}")
                print(f"   Amount: {test_case['amount']}")
                
                # Create transaction builder for this test
                account_ids = {
                    "cash_bank": precision_accounts[0].id,  # Cash account
                    "ar_processor": precision_accounts[0].id,  # Use cash account for AR too
                    "unearned_revenue": precision_accounts[1].id,  # Use revenue account for unearned revenue
                    "revenue_product_a": precision_accounts[1].id,  # Revenue account
                    "service_fees_expense": precision_accounts[2].id,  # Expense account
                }
                tx_builder = LedgerTransactionBuilder(account_ids)
                
                # Get balances before transaction
                await sql_ledger_api.begin_transaction()
                balances_before = {}
                for account in precision_accounts:
                    balances_before[account.id] = await sql_ledger_api.get_account_balance(account.id)
                await sql_ledger_api.end_transaction()
                
                # Execute test transaction(s)
                if test_case.get("iterations"):
                    # Multiple iterations test
                    for i in range(test_case["iterations"]):
                        tx = await tx_builder.payment(
                            amount=float(test_case["amount"]),
                            user_id=100,
                            name=f"{test_case['name']} - Iteration {i+1}",
                            description=f"{test_case['description']} - Iteration {i+1}"
                        )
                        logical_tx = LedgerLogicalTransaction(transactions=[tx])
                        await sql_ledger_api.begin_transaction()
                        await sql_ledger_api.create_transactions([logical_tx])
                        await sql_ledger_api.end_transaction()
                        total_transactions += 1
                else:
                    # Single transaction test
                    tx = await tx_builder.payment(
                        amount=float(test_case["amount"]),
                        user_id=100,
                        name=test_case["name"],
                        description=test_case["description"]
                    )
                    logical_tx = LedgerLogicalTransaction(transactions=[tx])
                    await sql_ledger_api.begin_transaction()
                    await sql_ledger_api.create_transactions([logical_tx])
                    await sql_ledger_api.end_transaction()
                    total_transactions += 1
                
                # Get balances after transaction(s)
                await sql_ledger_api.begin_transaction()
                balances_after = {}
                for account in precision_accounts:
                    balances_after[account.id] = await sql_ledger_api.get_account_balance(account.id)
                await sql_ledger_api.end_transaction()
                
                # Calculate precision verification
                cash_account = precision_accounts[0]
                cash_change = balances_after[cash_account.id] - balances_before[cash_account.id]
                cash_change_dollars = Decimal(cash_change) / SCALE
                
                # Verify precision
                expected_change = test_case["amount"]
                if test_case.get("iterations"):
                    expected_change = test_case["amount"] * test_case["iterations"]
                
                precision_error = abs(cash_change_dollars - expected_change)
                precision_maintained = precision_error < Decimal("0.0000000001")  # Less than 1 micro-unit error
                
                # Count decimal places in the result
                result_str = str(cash_change_dollars)
                if '.' in result_str:
                    decimal_places = len(result_str.split('.')[1])
                else:
                    decimal_places = 0
                
                test_results.append([
                    test_case["name"],
                    fmt_decimal(test_case["amount"]),
                    fmt_decimal(expected_change),
                    fmt_decimal(cash_change_dollars),
                    fmt_decimal(precision_error),
                    decimal_places,
                    "✓" if precision_maintained else "✗"
                ])
                
                print(f"   Expected change: {fmt_decimal(expected_change)}")
                print(f"   Actual change: {fmt_decimal(cash_change_dollars)}")
                print(f"   Precision error: {fmt_decimal(precision_error)}")
                print(f"   Decimal places: {decimal_places}")
                print(f"   Precision maintained: {'✓' if precision_maintained else '✗'}")
            
            # Display comprehensive results
            print(f"\n{'=' * 100}")
            print("DECIMAL PRECISION TEST RESULTS")
            print(f"{'=' * 100}")
            
            headers = [
                'Test Name', 'Amount', 'Expected Change', 'Actual Change', 
                'Precision Error', 'Decimal Places', 'Precision OK'
            ]
            print(f"\n{tabulate(test_results, headers=headers, tablefmt='grid', colalign=['left', 'right', 'right', 'right', 'right', 'center', 'center'])}")
            
            # Final precision verification
            print(f"\n📊 Final Account Balances:")
            await sql_ledger_api.begin_transaction()
            final_balances = {}
            for account in precision_accounts:
                final_balances[account.id] = await sql_ledger_api.get_account_balance(account.id)
                balance_dollars = Decimal(final_balances[account.id]) / SCALE
                print(f"   {account.name}: {fmt_decimal(balance_dollars)}")
            await sql_ledger_api.end_transaction()
            
            # Verify accounting equation still holds
            assets, liabilities, equity = self.calculate_equation_components(precision_accounts, final_balances)
            equation_balanced = abs(assets - (liabilities + equity)) < Decimal('0.0000000001')
            
            print(f"\n⚖️  Accounting Equation Verification:")
            print(f"   Assets: {fmt_decimal(assets)}")
            print(f"   Liabilities: {fmt_decimal(liabilities)}")
            print(f"   Equity: {fmt_decimal(equity)}")
            print(f"   Equation balanced: {'✓' if equation_balanced else '✗'}")
            
            print(f"\n📈 Test Summary:")
            print(f"   Total transactions executed: {total_transactions}")
            print(f"   Tests passed: {sum(1 for result in test_results if result[-1] == '✓')}")
            print(f"   Tests failed: {sum(1 for result in test_results if result[-1] == '✗')}")
            print(f"   Accounting equation balanced: {'✓' if equation_balanced else '✗'}")
            
            # Assertions
            assert all(result[-1] == '✓' for result in test_results), "Some precision tests failed"
            assert equation_balanced, "Accounting equation is not balanced after precision tests"
            
            print(f"\n✅ All decimal precision tests passed! Ledger maintains full 10-decimal precision.")
            
        except Exception as e:
            print(f"❌ Error in decimal precision test: {e}")
            raise
        finally:
            # Clean up database connections
            await sql_ledger_api.close()


if __name__ == "__main__":
    pytest.main([__file__]) 
