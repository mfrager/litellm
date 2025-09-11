"""
SQL Ledger Backend Implementation

This module provides a SQLAlchemy-based implementation of the LedgerAPI
for storing accounting data in a relational database.
"""

import json
from ulid import ULID
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Union, Dict, Any

from models.ledger_model import (
  SQLAccount,
  SQLAccountBalance,
  SQLAccountTransaction,
  SQLJournalEntry,
  SQLTransaction,
  SQLLedger,
  Base,
)

from .ledger_api import (
  LedgerAPI, 
  Ledger,
  LedgerAccount, 
  LedgerAccountBalance, 
  LedgerJournalEntry, 
  LedgerAccountTransfer,
  LedgerTransaction,
  LedgerAccountTransaction,
  LedgerTransferTransaction,
  LedgerLogicalTransaction,
  LedgerJournalTransaction,
  LedgerAccountFilter,
  LedgerQuery,
  AccountType,
  LedgerSide,
  TransactionType,
)

class SQLLedgerAPI(LedgerAPI):
  """
  SQL backend implementation of the LedgerAPI using SQLAlchemy.
  
  This implementation stores all ledger data in a relational database
  and provides ACID transaction support with trigger-based balance updates.
  """
  
  def __init__(self, ledger: Ledger, database_url: str):
    """
    Initialize the SQL Ledger API.
    
    Args:
      ledger: Ledger configuration
      database_url: SQLAlchemy async database URL (e.g., 'postgresql+asyncpg://user:pass@localhost/db')
    """
    super().__init__(ledger)
    self.engine = create_async_engine(database_url, echo=False)
    self.SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    self._session: Optional[AsyncSession] = None
    self.database_url = database_url
 
  async def begin_transaction(self) -> None:
    """Begin a database transaction."""
    if self._session is not None:
      raise RuntimeError("Transaction already active")
    
    self._session = self.SessionLocal()
    await self._session.begin()
  
  async def end_transaction(self) -> None:
    """Commit the current transaction."""
    if self._session is None:
      raise RuntimeError("No active transaction")
    
    try:
      await self._session.commit()
    finally:
      await self._session.close()
      self._session = None
  
  async def cancel_transaction(self) -> None:
    """Rollback the current transaction."""
    if self._session is None:
      raise RuntimeError("No active transaction")
    
    try:
      await self._session.rollback()
    finally:
      await self._session.close()
      self._session = None
  
  async def create_accounts(self, account_list: List[LedgerAccountTransaction]) -> None:
    """Create new ledger accounts."""
    session = self.get_session()
    
    for account_tx in account_list:
      for account in account_tx.accounts:
        # Convert string ID to ULID string, or generate new ULID if needed
        account_id = str(account.id) if account.id else str(ULID())
        
        sql_account = SQLAccount(
          id=account_id,
          name=account.name,
          account_type=account.account_type.value,
          side=account.side.value,
          owner_id=account.owner_id,
          is_promo=account.is_promo,
          decimals=account.decimals,
          currency=account.currency,
          details=json.dumps(account.details) if account.details else None,
          history=account.history,
          balance=0
        )
        
        try:
          session.add(sql_account)
          await session.flush()
        except IntegrityError as e:
          # Handle duplicate key error - account already exists
          if "Duplicate entry" in str(e) and "PRIMARY" in str(e):
            # Account already exists, continue without error
            await session.rollback()
            print(f"Account {account_id} already exists, skipping creation")
            continue
          else:
            # Re-raise other integrity errors
            raise e
  
  async def create_journal_entries(self, entry_list: List[LedgerJournalTransaction]) -> None:
    """Create new journal entries."""
    session = self.get_session()
    
    for entry_tx in entry_list:
      for entry in entry_tx.entries:
        # Convert string IDs to ULID strings
        entry_id = str(entry.id) if entry.id else str(ULID())
        
        account_id = entry.account_id
        transaction_id = str(entry.transaction_id) if entry.transaction_id else None
        
        sql_entry = SQLJournalEntry(
          id=entry_id,
          account_id=account_id,
          debit=entry.debit,
          credit=entry.credit,
          ts_created=entry.ts_created,
          transaction_id=transaction_id,
          description=entry.description
        )
        session.add(sql_entry)
    
    await session.flush()
  
  async def create_transfers(self, transfer_list: List[LedgerTransferTransaction]) -> None:
    """Create new transfers and corresponding account transactions."""
    session = self.get_session()
    
    for transfer_tx in transfer_list:
      for transfer in transfer_tx.transfers:
        # Convert string IDs to ULID strings
        transfer_id = str(transfer.id) if transfer.id else str(ULID())
        
        debit_account_id = transfer.debit_account_id
        credit_account_id = transfer.credit_account_id
        transaction_id = str(transfer.transaction_id) if transfer.transaction_id else None

        # Create the account transaction (triggers will update balances)
        account_tx_id = str(ULID())
        account_tx = SQLAccountTransaction(
          id=account_tx_id,
          src_id=credit_account_id,  # Source is credit account
          dst_id=debit_account_id,   # Destination is debit account
          amount=transfer.amount,
          ts_created=transfer.ts_created or datetime.now(timezone.utc),
          transaction_id=transaction_id,
          description=f"Transfer {transfer_id}"
        )
        session.add(account_tx)
    
    await session.flush()

  async def create_transactions(self, tx_list: List[LedgerLogicalTransaction]) -> None:
    """Create new transactions."""
    session = self.get_session()
    for logical_tx in tx_list:
      for tx in logical_tx.transactions:
        sql_tx_id = str(ULID())
        sql_tx = SQLTransaction(
          id=sql_tx_id,
          transaction_type=tx.transaction_type.value,
          user_id=tx.user_id,
          reference=tx.reference,
          description=tx.description,
          details=json.dumps(tx.details) if tx.details else None,
          ts_created=tx.ts_created or datetime.now(timezone.utc)  
        )
        session.add(sql_tx)
        await session.flush()
        if self.ledger.has_journal:
          for entry in tx.entries:
            entry.transaction_id = sql_tx_id
          await self.create_journal_entries([LedgerJournalTransaction(entries=tx.entries)])
        for transfer in tx.transfers:
          transfer.transaction_id = sql_tx_id
        await self.create_transfers([LedgerTransferTransaction(transfers=tx.transfers)])

  async def lookup_accounts(self, account_ids: List[Union[int, str]]) -> List[LedgerAccount]:
    """Fetch accounts by ID."""
    session = self.get_session()
    
    # Convert all IDs to string format
    ids = [str(aid) for aid in account_ids]
    
    result = await session.execute(select(SQLAccount).filter(SQLAccount.id.in_(ids)))
    sql_accounts = result.scalars().all()
    
    return [self._convert_sql_account_to_ledger_account(acc) for acc in sql_accounts]
  
  async def lookup_transfers(self, transfer_ids: List[Union[int, str]], with_balance: bool = True) -> List[LedgerAccountTransfer]:
    """Fetch transfers by ID."""
    session = self.get_session()
    
    # Convert all IDs to string format
    ids = [str(tid) for tid in transfer_ids]
    
    result = await session.execute(select(SQLAccountTransaction).filter(SQLAccountTransaction.id.in_(ids)))
    sql_transfers = result.scalars().all()
    
    transfers = []
    for transfer in sql_transfers:
      converted_transfer = self._convert_sql_account_transaction_to_ledger_transfer(transfer, with_balance=with_balance)
      transfers.append(converted_transfer)
    return transfers
  
  async def lookup_transactions(self, transaction_ids: List[Union[int, str]], 
              journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
    """Fetch transactions by ID."""
    session = self.get_session()
    
    # Convert all IDs to string format
    ids = [str(tid) for tid in transaction_ids]
    
    result = await session.execute(select(SQLTransaction).filter(SQLTransaction.id.in_(ids)))
    sql_transactions = result.scalars().all()
    
    return [self._convert_sql_transaction_to_ledger_transaction(tx, journal, transfers) 
        for tx in sql_transactions]
  
  async def lookup_entries(self, entry_ids: List[Union[int, str]]) -> List[LedgerJournalEntry]:
    """Fetch journal entries by ID."""
    session = self.get_session()
    
    # Convert all IDs to string format
    ids = [str(eid) for eid in entry_ids]
    
    result = await session.execute(select(SQLJournalEntry).filter(SQLJournalEntry.id.in_(ids)))
    sql_entries = result.scalars().all()
    
    return [self._convert_sql_entry_to_ledger_entry(entry) for entry in sql_entries]
  
  async def get_account_transfers(self, filter: LedgerAccountFilter, with_balance: bool = True) -> List[LedgerAccountTransfer]:
    """Fetch transfers involving a specific account."""
    session = self.get_session()
    
    query = select(SQLAccountTransaction)
    
    if filter.get('account_id'):
      account_id = str(filter['account_id'])
      query = query.filter(
        (SQLAccountTransaction.src_id == account_id) | 
        (SQLAccountTransaction.dst_id == account_id)
      )
    
    if filter.get('timestamp_min'):
      query = query.filter(SQLAccountTransaction.ts_created >= filter['timestamp_min'])
    
    if filter.get('timestamp_max'):
      query = query.filter(SQLAccountTransaction.ts_created <= filter['timestamp_max'])
    
    if filter.get('limit'):
      query = query.limit(filter['limit'])
    
    if filter.get('offset'):
      query = query.offset(filter['offset'])
    
    result = await session.execute(query)
    sql_transfers = result.scalars().all()
    
    transfers = []
    for transfer in sql_transfers:
      converted_transfer = self._convert_sql_account_transaction_to_ledger_transfer(transfer, with_balance=with_balance)
      transfers.append(converted_transfer)
    return transfers
  
  async def get_account_balances(self, filter: LedgerAccountFilter) -> List[LedgerAccountBalance]:
    """Fetch historical balances for an account."""
    session = self.get_session()
    
    query = select(SQLAccountBalance)
    
    if filter.get('account_id'):
      account_id = str(filter['account_id'])
      query = query.filter(SQLAccountBalance.account_id == account_id)
    
    if filter.get('timestamp_min'):
      query = query.filter(SQLAccountBalance.ts_created >= filter['timestamp_min'])
    
    if filter.get('timestamp_max'):
      query = query.filter(SQLAccountBalance.ts_created <= filter['timestamp_max'])
    
    # Order by timestamp (most recent first) BEFORE applying limit/offset
    query = query.order_by(SQLAccountBalance.ts_created.desc())
    
    if filter.get('limit'):
      query = query.limit(filter['limit'])
    
    if filter.get('offset'):
      query = query.offset(filter['offset'])
    
    result = await session.execute(query)
    sql_balances = result.scalars().all()
    
    return [self._convert_sql_balance_to_ledger_balance(balance) for balance in sql_balances]
  
  async def query_accounts(self, query: LedgerQuery) -> List[LedgerAccount]:
    """Query accounts by various fields."""
    session = self.get_session()
    
    q = select(SQLAccount)
    
    if query.get('account_id'):
      account_id = str(query['account_id'])
      q = q.filter(SQLAccount.id == account_id)
    
    if query.get('owner_id'):
      q = q.filter(SQLAccount.owner_id == query['owner_id'])
    
    if query.get('limit'):
      q = q.limit(query['limit'])
    
    if query.get('offset'):
      q = q.offset(query['offset'])
    
    result = await session.execute(q)
    sql_accounts = result.scalars().all()
    return [self._convert_sql_account_to_ledger_account(acc) for acc in sql_accounts]
  
  async def query_transfers(self, query: LedgerQuery, with_balance: bool = True) -> List[LedgerAccountTransfer]:
    """Query transfers by various fields."""
    session = self.get_session()
    
    q = select(SQLAccountTransaction)
    
    if query.get('transfer_id'):
      transfer_id = str(query['transfer_id'])
      q = q.filter(SQLAccountTransaction.id == transfer_id)
    
    if query.get('account_id'):
      account_id = str(query['account_id'])
      q = q.filter(
        (SQLAccountTransaction.src_id == account_id) | 
        (SQLAccountTransaction.dst_id == account_id)
      )
    
    if query.get('transaction_id'):
      transaction_id = str(query['transaction_id'])
      q = q.filter(SQLAccountTransaction.transaction_id == transaction_id)
    
    if query.get('timestamp_min'):
      q = q.filter(SQLAccountTransaction.ts_created >= query['timestamp_min'])
    
    if query.get('timestamp_max'):
      q = q.filter(SQLAccountTransaction.ts_created <= query['timestamp_max'])
    
    if query.get('limit'):
      q = q.limit(query['limit'])
    
    if query.get('offset'):
      q = q.offset(query['offset'])
    
    result = await session.execute(q)
    sql_transfers = result.scalars().all()
    
    transfers = []
    for transfer in sql_transfers:
      converted_transfer = self._convert_sql_account_transaction_to_ledger_transfer(transfer, with_balance=with_balance)
      transfers.append(converted_transfer)
    return transfers
  
  async def query_transactions(self, query: LedgerQuery, 
             journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
    """Query transactions by various fields."""
    session = self.get_session()
    
    q = select(SQLTransaction)
    
    if query.get('transaction_id'):
      transaction_id = str(query['transaction_id'])
      q = q.filter(SQLTransaction.id == transaction_id)
    
    if query.get('transaction_type'):
      q = q.filter(SQLTransaction.transaction_type == query['transaction_type'].value)
    
    if query.get('user_id'):
      q = q.filter(SQLTransaction.user_id == query['user_id'])
    
    if query.get('timestamp_min'):
      q = q.filter(SQLTransaction.ts_created >= query['timestamp_min'])
    
    if query.get('timestamp_max'):
      q = q.filter(SQLTransaction.ts_created <= query['timestamp_max'])
    
    if query.get('limit'):
      q = q.limit(query['limit'])
    
    if query.get('offset'):
      q = q.offset(query['offset'])
    
    result = await session.execute(q)
    sql_transactions = result.scalars().all()
    
    transactions = []
    for tx in sql_transactions:
      converted_tx = await self._convert_sql_transaction_to_ledger_transaction(tx, journal, transfers)
      transactions.append(converted_tx)
    return transactions
  
  async def query_journal(self, query: LedgerQuery) -> List[LedgerJournalEntry]:
    """Query journal entries by various fields."""
    session = self.get_session()
    
    q = select(SQLJournalEntry)
    
    if query.get('entry_id'):
      entry_id = str(query['entry_id'])
      q = q.filter(SQLJournalEntry.id == entry_id)
    
    if query.get('account_id'):
      account_id = str(query['account_id'])
      q = q.filter(SQLJournalEntry.account_id == account_id)
    
    if query.get('transaction_id'):
      transaction_id = str(query['transaction_id'])
      q = q.filter(SQLJournalEntry.transaction_id == transaction_id)
    
    if query.get('timestamp_min'):
      q = q.filter(SQLJournalEntry.ts_created >= query['timestamp_min'])
    
    if query.get('timestamp_max'):
      q = q.filter(SQLJournalEntry.ts_created <= query['timestamp_max'])
    
    if query.get('limit'):
      q = q.limit(query['limit'])
    
    if query.get('offset'):
      q = q.offset(query['offset'])
    
    result = await session.execute(q)
    sql_entries = result.scalars().all()
    return [self._convert_sql_entry_to_ledger_entry(entry) for entry in sql_entries]
  
  def _convert_sql_account_to_ledger_account(self, sql_account: SQLAccount) -> LedgerAccount:
    """Convert SQLAccount model to LedgerAccount pydantic model."""
    return LedgerAccount(
      id=sql_account.id,
      name=sql_account.name,
      account_type=AccountType(sql_account.account_type),
      side=LedgerSide(sql_account.side),
      owner_id=sql_account.owner_id,
      is_promo=sql_account.is_promo,
      decimals=sql_account.decimals,
      currency=sql_account.currency,
      details=json.loads(sql_account.details) if sql_account.details else None,
      history=sql_account.history
    )
  
  async def _convert_sql_transaction_to_ledger_transaction(self, sql_transaction: SQLTransaction, 
                           include_journal: bool = True, 
                           include_transfers: bool = True) -> LedgerTransaction:
    """Convert SQLTransaction model to LedgerTransaction pydantic model."""
    entries = None
    if include_journal and sql_transaction.journal_entries:
      entries = [self._convert_sql_entry_to_ledger_entry(entry) 
            for entry in sql_transaction.journal_entries]
    
    transfers = []
    if include_transfers and sql_transaction.transfers:
      for transfer in sql_transaction.transfers:
        converted_transfer = self._convert_sql_account_transaction_to_ledger_transfer(transfer)
        transfers.append(converted_transfer)
    
    return LedgerTransaction(
      id=sql_transaction.id,
      transaction_type=TransactionType(sql_transaction.transaction_type),
      entries=entries,
      transfers=transfers,
      ts_created=sql_transaction.ts_created,
      user_id=sql_transaction.user_id,
      reference=sql_transaction.reference,
      description=sql_transaction.description,
      details=json.loads(sql_transaction.details) if sql_transaction.details else None
    )
  
  def _convert_sql_entry_to_ledger_entry(self, sql_entry: SQLJournalEntry) -> LedgerJournalEntry:
    """Convert SQLJournalEntry model to LedgerJournalEntry pydantic model."""
    return LedgerJournalEntry(
      id=sql_entry.id,
      account_id=sql_entry.account_id,
      debit=sql_entry.debit,
      credit=sql_entry.credit,
      ts_created=sql_entry.ts_created,
      transaction_id=sql_entry.transaction_id if sql_entry.transaction_id else None,
      description=sql_entry.description
    )
  
  def _convert_sql_balance_to_ledger_balance(self, sql_balance: SQLAccountBalance) -> LedgerAccountBalance:
    """Convert SQLAccountBalance model to LedgerAccountBalance pydantic model."""
    return LedgerAccountBalance(
      account_id=sql_balance.account_id,
      balance=sql_balance.balance,
      ts_created=sql_balance.ts_created,
      last_transaction_id=sql_balance.this_tx if sql_balance.this_tx else None
    )
  
  def get_session(self) -> AsyncSession:
    """Get the current database session."""
    if self._session is None:
      raise RuntimeError("No active transaction")
    return self._session
  
  async def close_session(self) -> None:
    """Close the current database session."""
    if self._session is not None:
      await self._session.close()
      self._session = None
  
  async def get_account_balance(self, account_id: Union[int, str]) -> int:
    """Get current balance for an account."""
    session = self.get_session()
    account_id = str(account_id)
    
    result = await session.execute(select(SQLAccount).filter(SQLAccount.id == account_id))
    account = result.scalars().first()
    return account.balance if account else 0
  
  async def create_tables(self) -> None:
    """Create all database tables."""
    async with self.engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)
  
  async def close(self) -> None:
    """Close the database engine and clean up resources."""
    await self.engine.dispose()

  def _convert_sql_account_transaction_to_ledger_transfer(self, sql_transaction: SQLAccountTransaction, with_balance: bool = True) -> LedgerAccountTransfer:
    """Convert SQLAccountTransaction model to LedgerAccountTransfer pydantic model."""
    transfer_obj = LedgerAccountTransfer(
      id=sql_transaction.id,
      debit_account_id=sql_transaction.dst_id,  # Destination is debit account
      credit_account_id=sql_transaction.src_id,  # Source is credit account
      amount=sql_transaction.amount,
      ts_created=sql_transaction.ts_created,
      transaction_id=sql_transaction.transaction_id if sql_transaction.transaction_id else None
    )
    if with_balance:
      # For now, we'll set balance to None since we don't have the balance lookup logic
      # This could be enhanced later to fetch the actual balance
      transfer_obj.balance = None
    return transfer_obj

  async def _create_sqlite_triggers(self) -> None:
    """Create SQLite triggers for balance updates."""
    print("Creating SQLite triggers (async)...")

    # Create triggers directly using raw SQL
    async with self.engine.begin() as connection:
      # Drop existing triggers first
      try:
        await connection.execute(text("DROP TRIGGER IF EXISTS tx_transaction_insert"))
        await connection.execute(text("DROP TRIGGER IF EXISTS tx_balance_update"))
      except Exception as e:
        print(f"Note: Could not drop existing triggers: {e}")

      # Create transaction trigger
      tx_trigger_sql = """
      CREATE TRIGGER tx_transaction_insert
      AFTER INSERT ON ledger_account_transaction
      FOR EACH ROW
      BEGIN
        UPDATE ledger_accounts
        SET balance = balance - NEW.amount,
          ts_updated = NEW.ts_created,
          last_tx = NEW.id
        WHERE id = NEW.src_id;

        UPDATE ledger_accounts
        SET balance = balance + NEW.amount,
          ts_updated = NEW.ts_created,
          last_tx = NEW.id
        WHERE id = NEW.dst_id;
      END
      """

      # Create balance logging trigger
      balance_trigger_sql = """
      CREATE TRIGGER tx_balance_update
      AFTER UPDATE ON ledger_accounts
      FOR EACH ROW
      WHEN OLD.balance != NEW.balance
      BEGIN
        INSERT INTO ledger_account_log (account_id, last_tx, last_balance, this_tx, balance)
        VALUES (OLD.id, OLD.last_tx, OLD.balance, NEW.last_tx, NEW.balance);
      END
      """

      try:
        await connection.execute(text(tx_trigger_sql))
        print("✅ Created transaction trigger")
      except Exception as e:
        print(f"❌ Failed to create transaction trigger: {e}")

      try:
        await connection.execute(text(balance_trigger_sql))
        print("✅ Created balance logging trigger")
      except Exception as e:
        print(f"❌ Failed to create balance logging trigger: {e}")

    print("SQLite triggers creation completed.")

