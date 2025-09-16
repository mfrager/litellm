#!/usr/bin/env python3
"""
Chart of Accounts Management for Router Operations.

This module provides a centralized way to manage internal accounts and perform
balance checks for user operations.
"""

import os
import sys
import json
import logging
from typing import Dict, Optional, List, Tuple
from decimal import Decimal
from ulid import ULID

# Add the parent directory to the path to import ledger modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.ledger_api import LedgerAccount, AccountType, LedgerSide, LedgerAccountTransaction, Ledger
from ledger.ledger_tx_builder import LedgerTransactionBuilder
from ledger.sql_ledger import SQLLedgerAPI

from models.router_model import User, Workspace
from models.ledger_model import SQLAccount
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Constants
DECIMALS = 10  # 10 decimal places for high precision
SCALE = Decimal(10) ** DECIMALS
MINIMUM_BALANCE = Decimal("10.00")  # Minimum balance required for operations

class LedgerManager:
    """
    Manages the ledger and chart of accounts for router operations.
    
    This class provides methods to:
    - Find or create internal accounts
    - Check user balances
    - Perform balance validations
    - Access account IDs for transaction building
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the ledger manager.
        
        Args:
            session: SQLAlchemy async session for database operations
        """
        self.session = session
        
        # Create ledger configuration
        self.ledger_config = Ledger(
            id=1,
            accounts=[],
            has_journal=True,
            has_transactions=True,
            config={"currency": "USD", "decimals": DECIMALS}
        )
        
        # Create SQL Ledger API with the session
        self.sql_ledger_api = SQLLedgerAPI(self.ledger_config, session=session)
        self.internal_accounts: Dict[str, LedgerAccount] = {}
    
    async def get_account_id(self, account_code: str) -> str:
        """
        Get the account ID for a given account code.
        
        Args:
            account_code: The account code to look up
            
        Returns:
            The account ID
            
        Raises:
            ValueError: If account code is not found
        """
        # Find account on demand if not cached
        if account_code not in self.internal_accounts:
            await self.sql_ledger_api.begin_transaction()
            try:
                session = self.sql_ledger_api.get_session()
                
                # Direct SQL lookup by account code
                stmt = select(SQLAccount).where(SQLAccount.account_code == account_code)
                result = await session.execute(stmt)
                sql_account = result.scalar_one_or_none()
                
                if sql_account:
                    # Convert SQLAccount to LedgerAccount
                    ledger_account = LedgerAccount(
                        id=sql_account.id,
                        name=sql_account.name,
                        account_code=sql_account.account_code,
                        account_type=AccountType(sql_account.account_type),
                        side=LedgerSide(sql_account.side),
                        workspace_id=sql_account.workspace_id,
                        is_promo=sql_account.is_promo,
                        decimals=sql_account.decimals,
                        currency=sql_account.currency,
                        details=json.loads(sql_account.details) if sql_account.details else {},
                        history=sql_account.history,
                        balance=sql_account.balance,
                        last_tx=sql_account.last_tx,
                        ts_created=sql_account.ts_created,
                        ts_updated=sql_account.ts_updated
                    )
                    logging.warning(f"   ✅ Found existing account: {account_code}")
                    self.internal_accounts[account_code] = ledger_account
                else:
                    raise ValueError(f"Account '{account_code}' not found. All internal accounts must be pre-created.")
            finally:
                await self.sql_ledger_api.end_transaction()
        
        return self.internal_accounts[account_code].id
    
    
    async def get_workspace_balance_account(self, workspace: Workspace) -> Optional[LedgerAccount]:
        """
        Get the workspace's balance account.
        
        Args:
            workspace: The workspace object
            
        Returns:
            The workspace's balance account or None if not found
        """
        # Workspace account code format: "workspace_{workspace.id}_balance"
        account_code = f"workspace_{workspace.id}_balance"
        #logging.warning(f"account_code: {account_code}")
        
        await self.sql_ledger_api.begin_transaction()
        try:
            session = self.sql_ledger_api.get_session()
            
            # Direct SQL lookup by account code
            stmt = select(SQLAccount).where(SQLAccount.account_code == account_code)
            result = await session.execute(stmt)
            sql_account = result.scalar_one_or_none()

            #logging.warning(f"sql_account: {sql_account}")
            
            if sql_account:
                # Convert SQLAccount to LedgerAccount
                ledger_account = LedgerAccount(
                    id=sql_account.id,
                    name=sql_account.name,
                    account_code=sql_account.account_code,
                    account_type=AccountType(sql_account.account_type),
                    side=LedgerSide(sql_account.side),
                    workspace_id=sql_account.workspace_id,
                    is_promo=sql_account.is_promo,
                    decimals=sql_account.decimals,
                    currency=sql_account.currency,
                    details=json.loads(sql_account.details) if sql_account.details else {},
                    history=sql_account.history,
                    balance=sql_account.balance,
                    last_tx=sql_account.last_tx,
                    ts_created=sql_account.ts_created,
                    ts_updated=sql_account.ts_updated
                )
                return ledger_account
            
            return None
        finally:
            await self.sql_ledger_api.end_transaction()
    
    async def check_workspace_balance(self, workspace: Workspace) -> Tuple[bool, Decimal, Optional[str]]:
        """
        Check if workspace has sufficient balance for operations.
        
        Args:
            workspace: The workspace object
            
        Returns:
            Tuple of (has_sufficient_balance, current_balance, error_message)
        """

        #logging.warning(f"Checking workspace balance for workspace {workspace.id}")
        
        # Get workspace's balance account
        balance_account = await self.get_workspace_balance_account(workspace)
        
        if not balance_account:
            return False, Decimal("0"), f"No ledger account found."
        
        # Get current balance
        await self.sql_ledger_api.begin_transaction()
        try:
            balance_micro_units = await self.sql_ledger_api.get_account_balance(balance_account.id)
        finally:
            await self.sql_ledger_api.end_transaction()
        
        # Convert to decimal (balance is stored as negative for credit accounts)
        current_balance = Decimal(balance_micro_units) / SCALE
        
        # For unearned revenue (liability), negative balance means positive credit
        if current_balance < 0:
            available_balance = abs(current_balance)
        else:
            available_balance = current_balance
        
        has_sufficient_balance = available_balance >= MINIMUM_BALANCE
        
        if not has_sufficient_balance:
            error_msg = f"Required: ${MINIMUM_BALANCE}, Available: ${available_balance:.10f}"
        else:
            error_msg = None
        
        return has_sufficient_balance, available_balance, error_msg
    
    async def create_workspace_balance_account(self, workspace: Workspace) -> LedgerAccount:
        """
        Create a workspace balance account if it doesn't exist.
        
        Args:
            workspace: The workspace object
            
        Returns:
            The created or existing balance account
        """
        
        # Check if account already exists
        existing_account = await self.get_workspace_balance_account(workspace)
        if existing_account:
            return existing_account
        
        # Convert workspace ID to integer for ledger accounts
        workspace_id = hash(workspace.id) % 1000000
        
        # Create workspace balance account (Liability account for unearned revenue)
        workspace_balance_account = LedgerAccount(
            id=str(ULID()),
            name=f"Unearned Revenue - Workspace {workspace.id}",
            account_code=f"workspace_{workspace.id}_balance",
            account_type=AccountType.LIABILITY,
            side=LedgerSide.CREDIT,
            workspace_id=workspace_id,
            is_promo=False,
            decimals=DECIMALS,
            currency="USD",
            details={},
            history=True
        )
        
        # Create the account
        await self.sql_ledger_api.begin_transaction()
        try:
            await self.sql_ledger_api.create_accounts([
                LedgerAccountTransaction(accounts=[workspace_balance_account])
            ])
        finally:
            await self.sql_ledger_api.end_transaction()
        
        return workspace_balance_account
    
    async def create_transaction_builder(
        self, 
        account_codes: List[str]
    ) -> LedgerTransactionBuilder:
        """
        Create a LedgerTransactionBuilder with specified accounts.
        
        Args:
            account_codes: List of account codes to include. Must be provided explicitly.
                Available codes:
                - "ar_processor": For payment transactions (debit)
                - "unearned_revenue": For payment/purchase transactions (credit/debit)
                - "revenue_product_a": For purchase transactions (credit)
                - "cash_bank": For settlement transactions (debit)
                - "service_fees_expense": For expense transactions (debit)
        
        Returns:
            Configured LedgerTransactionBuilder instance
            
        Raises:
            ValueError: If account_codes is empty or contains invalid codes
        """
        if not account_codes:
            raise ValueError("account_codes cannot be empty. Available codes: ['ar_processor', 'unearned_revenue', 'revenue_product_a', 'cash_bank', 'service_fees_expense']")
        
        # Account code to internal account mapping
        account_mapping = {
            "ar_processor": "internal_cc_processor",
            "unearned_revenue": "internal_cash",  # Using cash for unearned revenue
            "revenue_product_a": "internal_revenue",
            "cash_bank": "internal_cash",
            "service_fees_expense": "internal_cost",
        }
        
        account_ids = {}
        
        # Add accounts based on the provided list
        for account_code in account_codes:
            if account_code in account_mapping:
                account_ids[account_code] = await self.get_account_id(account_mapping[account_code])
            else:
                raise ValueError(f"Unknown account code: {account_code}. Available codes: {list(account_mapping.keys())}")
        
        return LedgerTransactionBuilder(account_ids)
    
    def get_minimum_balance(self) -> Decimal:
        """Get the minimum balance required for operations."""
        return MINIMUM_BALANCE
    
