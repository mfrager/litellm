#!/usr/bin/env python3
"""
Test Runner for SQL Ledger API

This script demonstrates the SQL Ledger API functionality and runs basic tests.
"""

import os
import sys
import uuid
import tempfile
import asyncio
from dotenv import load_dotenv
from ulid import ULID
from tabulate import tabulate
from datetime import datetime
from typing import List, Dict, Any
from decimal import Decimal, getcontext, ROUND_HALF_UP

load_dotenv('../../../.env')
sys.path.append('../..')

from ledger.ledger_tx_builder import LedgerTransactionBuilder
from ledger.ledger_api import (
    Ledger,
    LedgerAccount,
    LedgerTransfer,
    LedgerTransaction,
    LedgerAccountTransaction,
    LedgerTransferTransaction,
    AccountType,
    LedgerSide,
    TransactionType
)
from ledger.sql_ledger import SQLLedgerAPI

# Pre-generate consistent ULIDs for test accounts
ACCOUNT_IDS = {
    # Internal company accounts (Owner ID: 100)
    "cash": str(ULID()),
    "sales_revenue": str(ULID()),
    "operating_expenses": str(ULID()),
    "accounts_receivable": str(ULID()),
    
    # Customer accounts (Owner ID: 200)
    "customer_credits": str(ULID()),
    "customer_deposits": str(ULID()),
    
    # Third-party payment processor accounts (Owner ID: 300)
    "cc_processor_payable": str(ULID()),
    "cc_processing_fees": str(ULID()),
    "tax_payable": str(ULID()),  # Keep tax as separate entity
    "ar_processor": str(ULID()), # Accounts Receivable (Credit Card Processor)
    "cash_bank": str(ULID()), # Cash/Bank Account
    "unearned_revenue": str(ULID()), # Unearned Revenue
    "revenue_product_a": str(ULID()), # Revenue – Product A
    "promo_revenue_product_a": str(ULID()), # Promo Revenue – Product A
    "service_fees_expense": str(ULID()), # Service Fees Expense
    "promo_expense": str(ULID()), # Promo Credit Expense
    "promo_liability": str(ULID()), # Promo Credit Liability (User 200)
}

# 1. Add promo-specific revenue account to ACCOUNT_IDS and create_sample_accounts
ACCOUNT_IDS["promo_revenue"] = str(ULID())

# 1. Add promo credit source account to ACCOUNT_IDS and create_sample_accounts
ACCOUNT_IDS["promo_credit_source"] = str(ULID())

# Set the number of decimals for all monetary calculations
DECIMALS = 6
SCALE = Decimal(10) ** DECIMALS
getcontext().prec = 28  # High precision for financial calculations

# Add a helper for formatting
DECIMAL_FMT = Decimal('0.000000')
def fmt_decimal(val):
    return f"${Decimal(val).quantize(DECIMAL_FMT, rounding=ROUND_HALF_UP).to_eng_string()}"


def create_sample_accounts() -> List[LedgerAccount]:
    """Create sample accounts for testing with proper entity separation, using canonical codes and owner_id for user-specific accounts."""
    return [
        # ============= ASSET ACCOUNTS (Owner ID: 100) =============
        LedgerAccount(
            id=ACCOUNT_IDS["ar_processor"],
            name="Accounts Receivable (Credit Card Processor)",
            account_type=AccountType.ASSET,
            side=LedgerSide.DEBIT,
            owner_id=100,
            is_promo=False,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Receivable from processor", "entity": "Internal Company"},
            history=True
        ),
        LedgerAccount(
            id=ACCOUNT_IDS["cash_bank"],
            name="Cash/Bank Account",
            account_type=AccountType.ASSET,
            side=LedgerSide.DEBIT,
            owner_id=100,
            is_promo=False,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Company cash/bank account", "entity": "Internal Company"},
            history=True
        ),
        # ============= LIABILITY ACCOUNTS =============
        LedgerAccount(
            id=ACCOUNT_IDS["unearned_revenue"],
            name="Unearned Revenue",
            account_type=AccountType.LIABILITY,
            side=LedgerSide.CREDIT,
            owner_id=200,  # user-specific
            is_promo=False,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Customer unearned revenue", "entity": "Customer"},
            history=True
        ),
        LedgerAccount(
            id=ACCOUNT_IDS["tax_payable"],
            name="Tax Payable",
            account_type=AccountType.LIABILITY,
            side=LedgerSide.CREDIT,
            owner_id=100,
            is_promo=False,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Sales tax payable", "entity": "Internal Company"},
            history=True
        ),
        LedgerAccount(
            id=ACCOUNT_IDS["promo_liability"],
            name="Promo Credit Liability (User 200)",
            account_type=AccountType.LIABILITY,
            side=LedgerSide.CREDIT,
            owner_id=200,  # user-specific
            is_promo=True,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Promo credit liability for user 200", "entity": "Customer"},
            history=True
        ),
        # ============= INCOME ACCOUNTS =============
        LedgerAccount(
            id=ACCOUNT_IDS["revenue_product_a"],
            name="Revenue – Product A",
            account_type=AccountType.INCOME,
            side=LedgerSide.CREDIT,
            owner_id=100,
            is_promo=False,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Product A revenue", "entity": "Internal Company"},
            history=True
        ),
        LedgerAccount(
            id=ACCOUNT_IDS["promo_revenue_product_a"],
            name="Promo Revenue – Product A",
            account_type=AccountType.INCOME,
            side=LedgerSide.CREDIT,
            owner_id=100,
            is_promo=True,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Promo revenue for Product A", "entity": "Internal Company"},
            history=True
        ),
        # ============= EXPENSE ACCOUNTS =============
        LedgerAccount(
            id=ACCOUNT_IDS["service_fees_expense"],
            name="Service Fees Expense",
            account_type=AccountType.EXPENSE,
            side=LedgerSide.DEBIT,
            owner_id=100,
            is_promo=False,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Service fees expense", "entity": "Internal Company"},
            history=True
        ),
        LedgerAccount(
            id=ACCOUNT_IDS["promo_expense"],
            name="Promo Credit Expense",
            account_type=AccountType.EXPENSE,
            side=LedgerSide.DEBIT,
            owner_id=100,
            is_promo=True,
            decimals=DECIMALS,
            currency="USD",
            details={"description": "Promo credit expense", "entity": "Internal Company"},
            history=True
        ),
    ]

# Now rewrite create_complex_transactions to use these accounts and canonical patterns

async def create_complex_transactions() -> List[Dict[str, Any]]:
    """Create a set of canonical, balanced business transactions for testing using the LedgerTransactionBuilder."""
    builder = LedgerTransactionBuilder(ACCOUNT_IDS)
    transactions = []
    
    # 1. Payment Authorization (customer pays $1000)
    tx_data = {
        "name": "Payment Authorization",
        "description": "Customer payment authorization",
        "user_id": 200,
    }
    tx_data["ledger_tx"] = await builder.payment(
        amount=1000, 
        user_id=tx_data["user_id"],
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    # 2. Revenue Recognition (Product A, $600)
    tx_data = {
        "name": "Revenue Recognition",
        "description": "Recognize revenue for Product A",
        "user_id": 200,
    }
    tx_data["ledger_tx"] = await builder.purchase(
        user_id=tx_data["user_id"], 
        product_amounts={"Product A": 600},
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    # 3. Settlement (funds from processor)
    tx_data = {
        "name": "Settlement",
        "description": "Settlement from processor",
        "user_id": 100,
    }
    tx_data["ledger_tx"] = await builder.settlement(
        amount=1000,
        user_id=tx_data["user_id"],
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    # 4. Service Fee Expense ($200)
    tx_data = {
        "name": "Service Fee Expense",
        "description": "Service fee expense",
        "user_id": 100,
    }
    tx_data["ledger_tx"] = await builder.expense(
        amount=200, 
        expense_type="service_fees",
        user_id=tx_data["user_id"],
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    # 5. Tax Collection ($60 on Product A)
    tx_data = {
        "name": "Tax Collection",
        "description": "Tax collected from customer",
        "user_id": 200,
    }
    tx_data["ledger_tx"] = await builder.tax_collection(
        revenue_amount=600, 
        tax_amount=60, 
        product="product_a",
        user_id=tx_data["user_id"],
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    # 6. Tax Remittance ($60)
    tx_data = {
        "name": "Tax Remittance",
        "description": "Remit tax to authority",
        "user_id": 100,
    }
    tx_data["ledger_tx"] = await builder.tax_remit(
        amount=60,
        user_id=tx_data["user_id"],
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    # 7. Promo Credit Issue ($200)
    tx_data = {
        "name": "Promo Credit Issue",
        "description": "Issue promo credit to user",
        "user_id": 200,
    }
    tx_data["ledger_tx"] = await builder.promo_issue(
        amount=200, 
        user_id=tx_data["user_id"],
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    # 8. Use Promo Credit ($150)
    tx_data = {
        "name": "Use Promo Credit",
        "description": "User uses promo credit for Product A",
        "user_id": 200,
    }
    tx_data["ledger_tx"] = await builder.promo_use(
        amount=150, 
        user_id=tx_data["user_id"], 
        product="product_a",
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    # 9. Cancel Promo Credit ($25)
    tx_data = {
        "name": "Cancel Promo Credit",
        "description": "Cancel unused promo credit",
        "user_id": 200,
    }
    tx_data["ledger_tx"] = await builder.promo_cancel(
        amount=25, 
        user_id=tx_data["user_id"],
        name=tx_data["name"],
        description=tx_data["description"]
    )
    transactions.append(tx_data)
    
    return transactions


async def analyze_account_impacts(api: SQLLedgerAPI, accounts: List[LedgerAccount], 
                          transactions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Analyze the impact of all transactions on each account."""
    await api.begin_transaction()
    
    account_impacts = {}
    account_transactions = {}
    
    # Initialize account impacts
    for account in accounts:
        account_impacts[account.id] = {
            "name": account.name,
            "type": account.account_type,
            "side": account.side,
            "debits": Decimal(0),  # store as micro-units
            "credits": Decimal(0),
            "net": Decimal(0),
            "balance": await api.get_account_balance(account.id)
        }
        account_transactions[account.id] = []
    
    # Analyze transfers involving each account
    for tx_info in transactions:
        for transfer in tx_info["ledger_tx"].transfers:
            # Debit account impact
            debit_account_id = transfer.debit_account_id
            if debit_account_id in account_impacts:
                account_impacts[debit_account_id]["debits"] += Decimal(transfer.amount)  # micro-units
                account_impacts[debit_account_id]["net"] += Decimal(transfer.amount)
                account_transactions[debit_account_id].append({
                    "transaction": tx_info["name"],
                    "description": tx_info["description"],
                    "amount": Decimal(transfer.amount),
                    "type": "debit",
                    "other_account": next((acc.name for acc in accounts if acc.id == transfer.credit_account_id), "Unknown"),
                    "transfer_id": transfer.id,
                    "transaction_id": transfer.transaction_id
                })
            
            # Credit account impact
            credit_account_id = transfer.credit_account_id
            if credit_account_id in account_impacts:
                account_impacts[credit_account_id]["credits"] += Decimal(transfer.amount)
                account_impacts[credit_account_id]["net"] -= Decimal(transfer.amount)
                account_transactions[credit_account_id].append({
                    "transaction": tx_info["name"],
                    "description": tx_info["description"],
                    "amount": Decimal(transfer.amount),
                    "type": "credit",
                    "other_account": next((acc.name for acc in accounts if acc.id == transfer.debit_account_id), "Unknown"),
                    "transfer_id": transfer.id,
                    "transaction_id": transfer.transaction_id
                })
    
    await api.end_transaction()
    
    return account_impacts, account_transactions


def display_detailed_account_balances(accounts: List[LedgerAccount], 
                                    account_impacts: Dict[str, Dict[str, Any]],
                                    account_transactions: Dict[str, List[Dict[str, Any]]]):
    """Display the detailed account balances with transactions analysis."""
    
    print("\n" + "=" * 100)
    print("DETAILED ACCOUNT BALANCES WITH TRANSACTIONS")
    print("=" * 100)
    
    # Group accounts by type
    accounts_by_type = {}
    for account in accounts:
        account_type = account.account_type.value.title()
        if account_type not in accounts_by_type:
            accounts_by_type[account_type] = []
        accounts_by_type[account_type].append(account)
    
    # Display each account type
    for account_type in sorted(accounts_by_type.keys()):
        print(f"\n{account_type.upper()} ACCOUNTS - DETAILED:")
        print("=" * 100)
        
        type_accounts = accounts_by_type[account_type]
        
        # Account summary table
        account_summary_data = []
        type_total = Decimal(0)
        
        for account in type_accounts:
            impact = account_impacts[account.id]
            balance = impact["balance"]
            
            # Convert balance from cents to dollars for display
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
            
            account_summary_data.append([
                account.id,
                account.name,
                balance_str,
                balance_type,
                account.owner_id,
                fmt_decimal(Decimal(impact['debits'])/SCALE),
                fmt_decimal(Decimal(impact['credits'])/SCALE)
            ])
            type_total += balance
        
        # Add total row
        total_dollars = Decimal(type_total) / SCALE
        total_str = fmt_decimal(total_dollars)
        if type_total < 0:
            total_str = f"({fmt_decimal(abs(total_dollars))})"
        
        total_balance_type = ""
        if type_total > 0:
            total_balance_type = "Dr" if account_type in ["Asset", "Expense"] else "Cr"
        elif type_total < 0:
            total_balance_type = "Cr" if account_type in ["Asset", "Expense"] else "Dr"
        else:
            total_balance_type = "-"
        
        account_summary_data.append([
            f"TOTAL {account_type.upper()}",
            "",
            total_str,
            total_balance_type,
            "",
            "",
            ""
        ])
        
        # Display accounts summary table
        headers = ['Account ID', 'Account Name', 'Final Balance', 'Type', 'Owner ID', 'Total Debits', 'Total Credits']
        print(f"\n{tabulate(account_summary_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'right', 'center', 'center', 'right', 'right'])}")
        
        # Collect and display all transactions for this account type
        all_transactions = []
        for account in type_accounts:
            if account.id in account_transactions:
                for tx_detail in account_transactions[account.id]:
                    all_transactions.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'transaction': tx_detail['transaction'],
                        'description': tx_detail['description'],
                        'amount': tx_detail['amount'],
                        'type': tx_detail['type'],
                        'other_account': tx_detail['other_account'],
                        'transaction_id': tx_detail['transaction_id']
                    })
        
        if all_transactions:
            print(f"\nTransactions affecting {account_type.upper()} accounts:")
            
            # Group transactions by transaction_id to show complete double-entry structure
            transactions_by_id = {}
            for tx in all_transactions:
                tx_id = tx['transaction_id']
                if tx_id not in transactions_by_id:
                    transactions_by_id[tx_id] = []
                transactions_by_id[tx_id].append(tx)
            
            # Prepare transaction data for table display
            transaction_data = []
            
            for tx_id, tx_group in transactions_by_id.items():
                for i, tx in enumerate(tx_group):
                    # Show transaction ID only for first entry
                    display_id = tx_id[:8] + "..." if i == 0 else ""
                    transaction_name = tx['transaction'] if i == 0 else ""
                    
                    # Format amount
                    amount_str = fmt_decimal(Decimal(tx['amount'])/SCALE)
                    debit_str = amount_str if tx['type'] == 'debit' else "-"
                    credit_str = amount_str if tx['type'] == 'credit' else "-"
                    
                    transaction_data.append([
                        display_id,
                        tx['account_id'],
                        tx['account_name'][:25],
                        tx['other_account'][:25],
                        debit_str,
                        credit_str,
                        transaction_name,
                        tx['description'][:30]
                    ])
            
            # Display transactions table
            headers = ['TX ID', 'Account ID', 'Account Name', 'Other Account', 'Debit', 'Credit', 'Transaction', 'Description']
            print(f"\n{tabulate(transaction_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'left', 'left', 'right', 'right', 'left', 'left'])}")
        else:
            print(f"\nNo transactions found for {account_type.upper()} accounts.")
        
        print()


def display_balance_sheet_summary(accounts: List[LedgerAccount], account_impacts: Dict[str, Dict[str, Any]]):
    """Display balance sheet summary with accounting equation verification."""
    print("\n" + "=" * 80)
    print("BALANCE SHEET SUMMARY")
    print("=" * 80)

    # Calculate totals by account type, using normal side logic
    totals_by_type = {
        "Asset": Decimal(0),
        "Liability": Decimal(0),
        "Income": Decimal(0),
        "Expense": Decimal(0)
    }

    for account in accounts:
        account_type = account.account_type.value.title()
        balance = account_impacts[account.id]["balance"]
        # Assets/Expenses: normal side is debit, so use balance as is
        # Liabilities/Income: normal side is credit, so use -balance
        if account_type in ["Liability", "Income"]:
            totals_by_type[account_type] += -balance
        else:
            totals_by_type[account_type] += balance

    # Convert to dollars and display
    for account_type, total_cents in totals_by_type.items():
        total_dollars = Decimal(total_cents) / SCALE
        print(f"Total {account_type}s:      {fmt_decimal(total_dollars)}")

    # Calculate net equity (Income - Expenses)
    net_equity_cents = totals_by_type["Income"] - totals_by_type["Expense"]
    net_equity_dollars = Decimal(net_equity_cents) / SCALE
    print(f"\nNet Equity (Income - Expenses): {fmt_decimal(net_equity_dollars)}")

    # Verify accounting equation: Assets = Liabilities + Equity
    assets_dollars = Decimal(totals_by_type["Asset"]) / SCALE
    liabilities_dollars = Decimal(totals_by_type["Liability"]) / SCALE

    equation_check = assets_dollars - (liabilities_dollars + net_equity_dollars)
    print(f"\nAccounting Equation Verification:")
    print(f"Assets = Liabilities + Equity")
    print(f"{fmt_decimal(assets_dollars)} = {fmt_decimal(liabilities_dollars)} + {fmt_decimal(net_equity_dollars)}")
    print(f"Difference: {fmt_decimal(equation_check)}")
    print(f"Equation Holds: {'✓' if abs(equation_check) < Decimal('0.000001') else '✗'}")


def render_user_account_ledger(
    sorted_tx,
    accounts,
    account_id_to_name,
    account_id_to_side,
    transaction_user_map,
    transaction_id_to_name,
    table_title,
    balance_col_labels,
    user_id,
    SCALE,
    fmt_decimal,
    is_promo=False
):
    print(f"\n{table_title}")
    if not accounts or not sorted_tx:
        print("No transactions found for these accounts.")
        return
    transaction_data = []
    running_balances = {acc.id: Decimal(0) for acc in accounts}
    for tx_id, tx_transfers in sorted_tx:
        tx_timestamp = tx_transfers[0].ts_created
        if tx_timestamp:
            tx_date = datetime.fromtimestamp(tx_timestamp).strftime("%Y-%m-%d %H:%M:%S")
        else:
            tx_date = "N/A"
        tx_user = transaction_user_map.get(tx_id)
        tx_desc = f"Transaction {tx_id[:8]}..."
        per_account_net = {acc.id: Decimal(0) for acc in accounts}
        account_balances_after_tx = {acc.id: None for acc in accounts}
        for transfer in tx_transfers:
            for acc in accounts:
                if transfer.balance is not None and getattr(transfer.balance, 'account_id', None) == acc.id:
                    account_balances_after_tx[acc.id] = transfer.balance.balance
                if transfer.debit_account_id == acc.id:
                    if account_id_to_side[acc.id] == LedgerSide.CREDIT:
                        per_account_net[acc.id] -= Decimal(transfer.amount)
                    else:
                        per_account_net[acc.id] += Decimal(transfer.amount)
                if transfer.credit_account_id == acc.id:
                    if account_id_to_side[acc.id] == LedgerSide.CREDIT:
                        per_account_net[acc.id] += Decimal(transfer.amount)
                    else:
                        per_account_net[acc.id] -= Decimal(transfer.amount)
        net = sum(per_account_net.values())
        for acc in accounts:
            if account_balances_after_tx[acc.id] is not None:
                running_balances[acc.id] = account_balances_after_tx[acc.id]
            else:
                running_balances[acc.id] += per_account_net[acc.id]
        tx_type = transaction_id_to_name.get(tx_id, "Unknown")
        row = [tx_date, tx_desc, tx_type, fmt_decimal(Decimal(net)/SCALE)]
        for acc in accounts:
            row.append(fmt_decimal(Decimal(running_balances[acc.id])/SCALE))
        transaction_data.append(row)
    headers = ["Date", "Transaction", "Type", "Net Amount"] + balance_col_labels
    print(f"\n{tabulate(transaction_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'left', 'right'] + ['right']*len(accounts))}")
    print(f"\n📊 {'Promo ' if is_promo else ''}User {user_id} Transaction Summary:")
    print(f"   • Total Transactions: {len(transaction_data)}")
    for acc in accounts:
        print(f"   • Final Balance in {account_id_to_name[acc.id]}: {fmt_decimal(Decimal(running_balances[acc.id])/SCALE)}")


async def display_user_transaction_report(api: SQLLedgerAPI, user_id: int, accounts: List[LedgerAccount], 
                                   transaction_user_map: Dict[str, int],
                                   transaction_id_to_name: Dict[str, str]):
    await api.begin_transaction()
    try:
        user_accounts = [acc for acc in accounts if acc.owner_id == user_id]
        if not user_accounts:
            return
        promo_account = next((acc for acc in user_accounts if "Promo Credit Liability" in acc.name), None)
        main_accounts = [acc for acc in user_accounts if acc != promo_account]
        main_account_ids = set(acc.id for acc in main_accounts)
        account_id_to_name = {acc.id: acc.name for acc in main_accounts}
        account_id_to_side = {acc.id: acc.side for acc in main_accounts}
        all_transfers = await api.query_transfers({}, with_balance=True)
        transfers_by_tx = {}
        for transfer in all_transfers:
            tx_id = transfer.transaction_id
            if tx_id not in transfers_by_tx:
                transfers_by_tx[tx_id] = []
            transfers_by_tx[tx_id].append(transfer)
        filtered_tx = []
        for tx_id, tx_transfers in transfers_by_tx.items():
            if any(t.debit_account_id in main_account_ids or t.credit_account_id in main_account_ids for t in tx_transfers):
                filtered_tx.append((tx_id, tx_transfers))
        sorted_tx = sorted(filtered_tx, key=lambda item: item[1][0].ts_created or 0)
        # Main table
        if main_accounts and sorted_tx:
            render_user_account_ledger(
                sorted_tx,
                main_accounts,
                account_id_to_name,
                account_id_to_side,
                transaction_user_map,
                transaction_id_to_name,
                table_title=f"\n{'='*100}\nUSER TRANSACTION REPORT - USER ID: {user_id} (Personal Bank Account View, Multi-Column)\n{'='*100}",
                balance_col_labels=[f"{account_id_to_name[acc.id]} Balance" for acc in main_accounts],
                user_id=user_id,
                SCALE=SCALE,
                fmt_decimal=fmt_decimal,
                is_promo=False
            )
        # Promo table
        if promo_account:
            promo_account_id = promo_account.id
            account_id_to_name_promo = {promo_account.id: promo_account.name}
            account_id_to_side_promo = {promo_account.id: promo_account.side}
            filtered_promo_tx = []
            for tx_id, tx_transfers in transfers_by_tx.items():
                if any(t.debit_account_id == promo_account_id or t.credit_account_id == promo_account_id for t in tx_transfers):
                    filtered_promo_tx.append((tx_id, tx_transfers))
            sorted_promo_tx = sorted(filtered_promo_tx, key=lambda item: item[1][0].ts_created or 0)
            render_user_account_ledger(
                sorted_promo_tx,
                [promo_account],
                account_id_to_name_promo,
                account_id_to_side_promo,
                transaction_user_map,
                transaction_id_to_name,
                table_title=f"\n{'='*100}\nCUSTOMER PROMOTIONAL CREDITS LEDGER\n{'='*100}",
                balance_col_labels=[f"{promo_account.name} Balance"],
                user_id=user_id,
                SCALE=SCALE,
                fmt_decimal=fmt_decimal,
                is_promo=True
            )
    except Exception as e:
        print(f"❌ Error generating user transaction report: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await api.end_transaction()



async def run_demo():
    """Run a demonstration of the SQL Ledger API with detailed account analysis."""
    print("🏦 SQL Ledger API Demo - MULTI-ENTITY DETAILED ACCOUNT BALANCES")
    print("=" * 100)
    print("📋 Entity Structure:")
    print("   • Owner ID 100: Internal Company (Cash, Revenue, Expenses, Receivables)")
    print("   • Owner ID 200: Customer Accounts (Credits, Deposits)")
    print("   • Owner ID 300: Payment Processor (Payables, Processing Fees)")
    print("   • Owner ID 400: Tax Authority (Tax Payables)")
    print("=" * 100)
    
    # Create temporary SQLite database
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_file.close()
    database_url = f"sqlite+aiosqlite:///{temp_file.name}"
    
    try:
        # Initialize ledger
        ledger = Ledger(
            id=1,
            accounts=[],
            has_journal=True,
            has_transactions=True,
            config={"name": "Demo Ledger", "version": "1.0"}
        )
        
        print(f"🗄️  Creating SQLite database: {temp_file.name}")
        api = SQLLedgerAPI(ledger, database_url)
        
        # Create database tables
        print("📋 Creating database tables...")
        await api.create_tables()
        print("   ✅ Database tables created")
        
        # Create accounts
        print("\n📊 Creating comprehensive chart of accounts...")
        accounts = create_sample_accounts()
        account_transaction = LedgerAccountTransaction(accounts=accounts)
        
        await api.begin_transaction()
        await api.create_accounts([account_transaction])
        await api.end_transaction()
        
        print(f"   ✅ Created {len(accounts)} accounts")
        
        # Display chart of accounts
        print("\n" + "=" * 80)
        print("CHART OF ACCOUNTS")
        print("=" * 80)
        
        chart_data = []
        for account in accounts:
            chart_data.append([
                account.id,
                account.name,
                account.account_type.value.title(),
                account.side.value.title(),
                account.owner_id,
                "Yes" if account.is_promo else "No",
                account.details.get("entity", "N/A")
            ])
        
        headers = ['Account ID', 'Account Name', 'Type', 'Normal Side', 'Owner ID', 'Promotional', 'Entity']
        print(f"\n{tabulate(chart_data, headers=headers, tablefmt='grid', colalign=['left', 'left', 'left', 'center', 'center', 'center', 'left'])}")
        
        # Check initial balances
        print("\n💰 Initial account balances:")
        await api.begin_transaction()
        initial_balances = []
        for account in accounts:
            balance = await api.get_account_balance(account.id)
            initial_balances.append([account.name, account.owner_id, fmt_decimal(Decimal(balance)/SCALE)])
        await api.end_transaction()
        
        print(f"\n{tabulate(initial_balances, headers=['Account', 'Owner ID', 'Balance'], tablefmt='grid', colalign=['left', 'center', 'right'])}")
        
        # Create complex business transactions
        print("\n📝 Creating complex business transactions...")
        transactions = await create_complex_transactions()
        
        transaction_summary = []
        created_transaction_ids = []  # Track created transaction IDs for user report
        transaction_user_map = {}  # Map transaction IDs to user IDs for reporting
        transaction_id_to_name = {}  # Map transaction IDs to transaction names for reporting
        
        for i, tx_info in enumerate(transactions, 1):
            # Generate a consistent transaction ID for all transfers in this transaction
            transaction_id = str(ULID())
            
            # Update transfer transaction_ids to match our transaction
            for transfer in tx_info["ledger_tx"].transfers:
                transfer.transaction_id = transaction_id
            
            # Create the transfers
            transfer_transaction = LedgerTransferTransaction(transfers=tx_info["ledger_tx"].transfers)
            
            await api.begin_transaction()
            await api.create_transfers([transfer_transaction])
            await api.end_transaction()
            
            created_transaction_ids.append(transaction_id)
            transaction_user_map[transaction_id] = tx_info["user_id"]
            transaction_id_to_name[transaction_id] = tx_info["name"]
            
            total_amount = sum(Decimal(transfer.amount) / SCALE for transfer in tx_info["ledger_tx"].transfers)
            transaction_summary.append([
                i,
                tx_info["name"],
                tx_info["description"],
                tx_info["user_id"],
                fmt_decimal(total_amount),
                len(tx_info["ledger_tx"].transfers)
            ])
        
        print(f"   ✅ Created {len(transactions)} complex transactions")
        
        # Display transaction summary
        print("\n" + "=" * 80)
        print("TRANSACTION SUMMARY")
        print("=" * 80)
        
        headers = ['#', 'Transaction Name', 'Description', 'User ID', 'Amount', 'Transfers']
        print(f"\n{tabulate(transaction_summary, headers=headers, tablefmt='grid', colalign=['center', 'left', 'left', 'center', 'right', 'center'])}")
        
        # Analyze account impacts
        print("\n🔍 Analyzing account impacts and transaction history...")
        account_impacts, account_transactions = await analyze_account_impacts(api, accounts, transactions)
        
        # Display detailed account balances with transactions
        display_detailed_account_balances(accounts, account_impacts, account_transactions)
        
        # Display balance sheet summary
        display_balance_sheet_summary(accounts, account_impacts)
        
        # Display balance history analysis
        print("\n" + "=" * 80)
        print("BALANCE HISTORY ANALYSIS")
        print("=" * 80)
        
        await api.begin_transaction()
        
        history_summary = []
        for account in accounts:
            history = await api.get_account_balances({"account_id": account.id, "limit": 10})
            transfers = await api.get_account_transfers({"account_id": account.id, "limit": 10})
            
            history_summary.append([
                account.id,
                account.name,
                account.owner_id,
                len(history),
                len(transfers),
                fmt_decimal(Decimal(account_impacts[account.id]['balance'])/SCALE)
            ])
        
        await api.end_transaction()
        
        headers = ['Account ID', 'Account Name', 'Owner ID', 'History Entries', 'Transfers', 'Final Balance']
        print(f"\n{tabulate(history_summary, headers=headers, tablefmt='grid', colalign=['left', 'left', 'center', 'center', 'center', 'right'])}")
        
        # Display user transaction reports for key users
        print("\n" + "=" * 100)
        print("USER TRANSACTION REPORTS")
        print("=" * 100)
        
        # Report for User 101 (Sales team)
        await display_user_transaction_report(api, 101, accounts, transaction_user_map, transaction_id_to_name)
        
        # Report for User 102 (Finance team)
        await display_user_transaction_report(api, 102, accounts, transaction_user_map, transaction_id_to_name)

        # Report for User 200 (Customer)
        await display_user_transaction_report(api, 200, accounts, transaction_user_map, transaction_id_to_name)
        
        print("\n✅ Detailed analysis completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        try:
            await api.close()
        except:
            pass
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
            print(f"\n🧹 Cleaned up database file: {temp_file.name}")


async def run_basic_tests():
    """Run basic functionality tests."""
    print("\n🧪 Running Basic Tests")
    print("=" * 50)
    
    # Create temporary SQLite database
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_file.close()
    database_url = f"sqlite+aiosqlite:///{temp_file.name}"
    
    try:
        ledger = Ledger(
            id=1,
            accounts=[],
            has_journal=True,
            has_transactions=True,
            config={}
        )
        
        api = SQLLedgerAPI(ledger, database_url)
        
        # Create database tables
        print("📋 Creating database tables...")
        await api.create_tables()
        print("   ✅ Database tables created")
        
        # Test 1: Transaction lifecycle
        print("Test 1: Transaction lifecycle...")
        await api.begin_transaction()
        assert api._session is not None, "Session should be active"
        await api.end_transaction()
        assert api._session is None, "Session should be closed"
        print("   ✅ Passed")
        
        # Test 2: Account creation and lookup
        print("Test 2: Account creation and lookup...")
        # Select the first 4 internal company accounts (owner_id=100)
        all_accounts = create_sample_accounts()
        accounts = [acc for acc in all_accounts if acc.owner_id == 100][:4]
        
        await api.begin_transaction()
        await api.create_accounts([LedgerAccountTransaction(accounts=accounts)])
        created_accounts = await api.lookup_accounts([acc.id for acc in accounts])
        await api.end_transaction()
        
        assert len(created_accounts) == 4, f"Expected 4 accounts, got {len(created_accounts)}"
        
        # Match accounts by ID instead of assuming order
        created_by_id = {acc.id: acc for acc in created_accounts}
        for original_account in accounts:
            assert original_account.id in created_by_id, f"Account {original_account.id} not found in lookup results"
            created_account = created_by_id[original_account.id]
            assert created_account.name == original_account.name, f"Account name mismatch: {created_account.name} != {original_account.name}"
        
        print("   ✅ Passed")
        
        # Test 3: Transfer creation and balance updates
        print("Test 3: Transfer creation and balance updates...")
        transfer = LedgerTransfer(
            id=str(ULID()),
            debit_account_id=accounts[0].id,  # company cash
            credit_account_id=accounts[1].id,  # sales_revenue
            amount=10000 * SCALE,  # $100.00
            timestamp=int(datetime.now().timestamp()),
            transaction_id=str(ULID())
        )
        
        await api.begin_transaction()
        initial_balance_cash = await api.get_account_balance(accounts[0].id)
        initial_balance_revenue = await api.get_account_balance(accounts[1].id)
        
        await api.create_transfers([LedgerTransferTransaction(transfers=[transfer])])
        
        final_balance_cash = await api.get_account_balance(accounts[0].id)
        final_balance_revenue = await api.get_account_balance(accounts[1].id)
        await api.end_transaction()
        
        # Cash should increase by $100, Revenue should decrease by $100 (because it's credited)
        assert final_balance_cash == initial_balance_cash + 10000 * SCALE, "Cash balance not updated correctly"
        assert final_balance_revenue == initial_balance_revenue - 10000 * SCALE, "Revenue balance not updated correctly"
        print("   ✅ Passed")
        
        # Test 4: Query operations
        print("Test 4: Query operations...")
        await api.begin_transaction()
        
        # Query internal company accounts (owner_id=100)
        query_results = await api.query_accounts({"owner_id": 100})
        assert len(query_results) == 4, f"Expected 4 internal company accounts for owner 100, got {len(query_results)}"
        
        # Query transfers
        transfer_results = await api.query_transfers({"account_id": accounts[0].id})
        assert len(transfer_results) == 1, f"Expected 1 transfer for cash account, got {len(transfer_results)}"
        
        await api.end_transaction()
        print("   ✅ Passed")
        
        print("\n✅ All basic tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        try:
            await api.close()
        except:
            pass
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


async def main():
    print("🚀 SQL Ledger API Test Suite - COMPREHENSIVE ANALYSIS")
    print("=" * 100)
    
    # Run comprehensive demo with detailed account balances
    await run_demo()
    
    # Run basic functionality tests
    await run_basic_tests()
    

if __name__ == "__main__":
    asyncio.run(main())
    
    print("\n🎉 Comprehensive test suite completed!")
    print("=" * 100)
    print("This analysis demonstrates:")
    print("✅ Complete double-entry bookkeeping with audit trails")
    print("✅ Real-time balance updates via database triggers") 
    print("✅ Comprehensive transaction history and impact analysis")
    print("✅ Balance sheet verification with accounting equation")
    print("✅ Multi-account type support (Assets, Liabilities, Income, Expenses)")
    print("✅ Professional financial reporting capabilities")
    print("✅ Async SQLAlchemy integration with comprehensive testing")
    print("=" * 100) 
