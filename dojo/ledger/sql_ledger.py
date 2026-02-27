"""
SQL Ledger Backend Implementation

This module provides a SQLAlchemy-based implementation of the LedgerAPI
for storing accounting data in a relational database.
"""

import json
from ulid import ULID
from dojo.models.functions import generate_ulid
from datetime import datetime, timezone
from sqlalchemy import text, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Union

from dojo.models.ledger_model import (
  SQLAccount,
  SQLAccountBalance,
  SQLAccountTransaction,
  SQLJournalEntry,
  SQLTransaction,
  Base,
)

def _ulid_bytes(val):
  """Normalize ID to 16-byte ULID bytes. Accepts bytes or str (Crockford base32)."""
  if val is None:
    return None
  if isinstance(val, bytes):
    return val
  if isinstance(val, str):
    return ULID.from_str(val).bytes
  return None

class _BytesEncoder(json.JSONEncoder):
  """JSON encoder that converts bytes to their hex representation."""
  def default(self, o):
    if isinstance(o, bytes):
      return o.hex()
    return super().default(o)

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
  
  def __init__(self, ledger: Ledger, database_url: Optional[str] = None, session: Optional[AsyncSession] = None):
    """
    Initialize the SQL Ledger API.
    
    Args:
      ledger: Ledger configuration
      database_url: SQLAlchemy async database URL (e.g., 'postgresql+asyncpg://user:pass@localhost/db')
      session: Optional existing AsyncSession to use instead of creating new connections
    """
    super().__init__(ledger)
    
    if session is not None:
      # Use provided session
      self._session = session
      self.engine = None
      self.SessionLocal = None
      self.database_url = None
      self._external_session = True
    elif database_url is not None:
      # Create new engine and session factory with robust settings for testing
      self.engine = create_async_engine(
          database_url, 
          echo=False,
          pool_pre_ping=True,
          pool_recycle=300,
          pool_timeout=30
      )
      self.SessionLocal = async_sessionmaker(
          autocommit=False, 
          autoflush=False, 
          bind=self.engine,
          expire_on_commit=False
      )
      self._session: Optional[AsyncSession] = None
      self.database_url = database_url
      self._external_session = False
    else:
      raise ValueError("Either database_url or session must be provided")
 
  async def begin_transaction(self) -> None:
    """Begin a database transaction."""
    if self._external_session:
      # External session - assume it's already in a transaction
      pass
    else:
      # Check if we already have a session
      if self._session is not None:
        raise RuntimeError("Transaction already active")
      
      # Create new session and begin transaction
      assert self.SessionLocal is not None
      self._session = self.SessionLocal()
      await self._session.begin()
  
  async def end_transaction(self) -> None:
    """Commit the current transaction."""
    if self._session is None:
      raise RuntimeError("No active transaction")
    
    if self._external_session:
      # External session - don't commit or close, let caller handle it
      pass
    else:
      # Own session - commit and close
      try:
        await self._session.commit()
      finally:
        await self._session.close()
        self._session = None
  
  async def cancel_transaction(self) -> None:
    """Rollback the current transaction."""
    if self._session is None:
      raise RuntimeError("No active transaction")
    
    if self._external_session:
      # External session - don't rollback or close, let caller handle it
      pass
    else:
      # Own session - rollback and close
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
        account_id = _ulid_bytes(account.id) if account.id else generate_ulid()
        workspace_id = _ulid_bytes(account.workspace_id) if account.workspace_id else None
        sql_account = SQLAccount(  # type: ignore[call-arg]
          id=account_id,  # type: ignore[call-arg]
          name=account.name,  # type: ignore[call-arg]
          account_code=account.account_code,  # type: ignore[call-arg]
          account_type=account.account_type.value,  # type: ignore[call-arg]
          side=account.side.value,  # type: ignore[call-arg]
          workspace_id=workspace_id,  # type: ignore[call-arg]
          is_promo=account.is_promo,  # type: ignore[call-arg]
          decimals=account.decimals,  # type: ignore[call-arg]
          currency=account.currency,  # type: ignore[call-arg]
          details=json.dumps(account.details) if account.details else None,  # type: ignore[call-arg]
          history=account.history,  # type: ignore[call-arg]
          balance=0  # type: ignore[call-arg]
        )
        
        try:
          session.add(sql_account)
          await session.flush()
        except IntegrityError as e:
          # Handle duplicate key error - account already exists
          if "Duplicate entry" in str(e) and "PRIMARY" in str(e):
            # Account already exists, continue without error
            await session.rollback()
            print(f"Account {account_id!r} already exists, skipping creation")
            continue
          else:
            # Re-raise other integrity errors
            raise e
  
  async def create_journal_entries(self, entry_list: List[LedgerJournalTransaction]) -> None:
    """Create new journal entries."""
    session = self.get_session()
    
    for entry_tx in entry_list:
      for entry in entry_tx.entries:
        entry_id = _ulid_bytes(entry.id) if entry.id else generate_ulid()
        account_id = _ulid_bytes(entry.account_id) if entry.account_id else None
        transaction_id = _ulid_bytes(entry.transaction_id) if entry.transaction_id else None
        
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
        transfer_id = _ulid_bytes(transfer.id) if transfer.id else generate_ulid()
        debit_account_id = _ulid_bytes(transfer.debit_account_id) if transfer.debit_account_id else None
        credit_account_id = _ulid_bytes(transfer.credit_account_id) if transfer.credit_account_id else None
        transaction_id = _ulid_bytes(transfer.transaction_id) if transfer.transaction_id else None

        account_tx_id = generate_ulid()
        account_tx = SQLAccountTransaction(
          id=account_tx_id,
          src_id=credit_account_id,  # Source is credit account
          dst_id=debit_account_id,   # Destination is debit account
          amount=transfer.amount,
          ts_created=transfer.ts_created or datetime.now(timezone.utc),
          transaction_id=transaction_id,
          description=f"Transfer {transfer_id!r}"
        )
        session.add(account_tx)
        # Application-level balance update only when DB does not use triggers (e.g. SQLite).
        # When balance_via_trigger is True (e.g. MySQL with mysql_triggers.sql), the DB trigger updates balance.
        if not (self.ledger.config or {}).get("balance_via_trigger"):
          if debit_account_id is not None:
            await session.execute(
              update(SQLAccount)
              .where(SQLAccount.id == debit_account_id)
              .values(balance=SQLAccount.balance + transfer.amount)
            )
          if credit_account_id is not None:
            await session.execute(
              update(SQLAccount)
              .where(SQLAccount.id == credit_account_id)
              .values(balance=SQLAccount.balance - transfer.amount)
            )
    
    await session.flush()

  async def create_transactions(self, tx_list: List[LedgerLogicalTransaction]) -> None:
    """Create new transactions."""
    session = self.get_session()
    for logical_tx in tx_list:
      for tx in logical_tx.transactions:
        sql_tx_id = generate_ulid()
        user_id = _ulid_bytes(tx.user_id) if tx.user_id else None
        sql_tx = SQLTransaction(
          id=sql_tx_id,
          transaction_type=tx.transaction_type.value,
          user_id=user_id,
          reference=tx.reference,
          description=tx.description,
          details=json.dumps(tx.details, cls=_BytesEncoder) if tx.details else None,
          ts_created=tx.ts_created or datetime.now(timezone.utc)  
        )
        session.add(sql_tx)
        await session.flush()
        if self.ledger.has_journal and tx.entries:
          for entry in tx.entries:
            entry.transaction_id = sql_tx_id
          await self.create_journal_entries([LedgerJournalTransaction(entries=tx.entries)])
        for transfer in tx.transfers:
          transfer.transaction_id = sql_tx_id
        await self.create_transfers([LedgerTransferTransaction(transfers=tx.transfers)])

  async def lookup_accounts(self, account_ids: List[Union[int, str, bytes]]) -> List[LedgerAccount]:
    """Fetch accounts by ID."""
    session = self.get_session()
    ids = [b for aid in account_ids if (b := _ulid_bytes(aid)) is not None]
    if not ids:
      return []
    result = await session.execute(select(SQLAccount).filter(SQLAccount.id.in_(ids)))
    sql_accounts = result.scalars().all()
    
    return [self._convert_sql_account_to_ledger_account(acc) for acc in sql_accounts]
  
  async def lookup_transfers(self, transfer_ids: List[Union[int, str, bytes]], with_balance: bool = True) -> List[LedgerAccountTransfer]:
    """Fetch transfers by ID."""
    session = self.get_session()
    ids = [b for tid in transfer_ids if (b := _ulid_bytes(tid)) is not None]
    if not ids:
      return []
    result = await session.execute(select(SQLAccountTransaction).filter(SQLAccountTransaction.id.in_(ids)))
    sql_transfers = result.scalars().all()
    
    transfers = []
    for transfer in sql_transfers:
      converted_transfer = self._convert_sql_account_transaction_to_ledger_transfer(transfer, with_balance=with_balance)
      transfers.append(converted_transfer)
    return transfers
  
  async def lookup_transactions(self, transaction_ids: List[Union[int, str, bytes]], 
              journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
    """Fetch transactions by ID."""
    session = self.get_session()
    ids = [b for tid in transaction_ids if (b := _ulid_bytes(tid)) is not None]
    if not ids:
      return []
    result = await session.execute(select(SQLTransaction).filter(SQLTransaction.id.in_(ids)))
    sql_transactions = result.scalars().all()
    
    results: List[LedgerTransaction] = []
    for tx in sql_transactions:
      results.append(await self._convert_sql_transaction_to_ledger_transaction(tx, journal, transfers))
    return results
  
  async def lookup_entries(self, entry_ids: List[Union[int, str, bytes]]) -> List[LedgerJournalEntry]:
    """Fetch journal entries by ID."""
    session = self.get_session()
    ids = [b for eid in entry_ids if (b := _ulid_bytes(eid)) is not None]
    if not ids:
      return []
    result = await session.execute(select(SQLJournalEntry).filter(SQLJournalEntry.id.in_(ids)))
    sql_entries = result.scalars().all()
    
    return [self._convert_sql_entry_to_ledger_entry(entry) for entry in sql_entries]
  
  async def get_account_transfers(self, filter: LedgerAccountFilter, with_balance: bool = True) -> List[LedgerAccountTransfer]:
    """Fetch transfers involving a specific account."""
    session = self.get_session()
    
    query = select(SQLAccountTransaction)
    
    if filter.get('account_id'):
      account_id = _ulid_bytes(filter.get('account_id'))
      if account_id is not None:
        query = query.filter(
          (SQLAccountTransaction.src_id == account_id) |
          (SQLAccountTransaction.dst_id == account_id)
        )
    
    if filter.get('timestamp_min'):
      query = query.filter(SQLAccountTransaction.ts_created >= filter.get('timestamp_min'))
    
    if filter.get('timestamp_max'):
      query = query.filter(SQLAccountTransaction.ts_created <= filter.get('timestamp_max'))
    
    if filter.get('limit'):
      query = query.limit(filter.get('limit'))
    
    if filter.get('offset'):
      query = query.offset(filter.get('offset'))
    
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
      account_id = _ulid_bytes(filter.get('account_id'))
      if account_id is not None:
        query = query.filter(SQLAccountBalance.account_id == account_id)
    
    if filter.get('timestamp_min'):
      query = query.filter(SQLAccountBalance.ts_created >= filter.get('timestamp_min'))
    
    if filter.get('timestamp_max'):
      query = query.filter(SQLAccountBalance.ts_created <= filter.get('timestamp_max'))
    
    # Order by timestamp (most recent first) BEFORE applying limit/offset
    query = query.order_by(SQLAccountBalance.ts_created.desc())
    
    if filter.get('limit'):
      query = query.limit(filter.get('limit'))
    
    if filter.get('offset'):
      query = query.offset(filter.get('offset'))
    
    result = await session.execute(query)
    sql_balances = result.scalars().all()
    
    return [self._convert_sql_balance_to_ledger_balance(balance) for balance in sql_balances]
  
  async def query_accounts(self, query: LedgerQuery) -> List[LedgerAccount]:
    """Query accounts by various fields."""
    session = self.get_session()
    
    q = select(SQLAccount)
    
    if query.get('account_id'):
      account_id = _ulid_bytes(query.get('account_id'))
      if account_id is not None:
        q = q.filter(SQLAccount.id == account_id)
    
    if query.get('workspace_id'):
      wid_raw = query.get('workspace_id')
      wid = _ulid_bytes(wid_raw) if isinstance(wid_raw, (str, bytes)) else wid_raw
      q = q.filter(SQLAccount.workspace_id == wid)
    
    if query.get('name'):
      q = q.filter(SQLAccount.name == query.get('name'))
    
    if query.get('account_code'):
      q = q.filter(SQLAccount.account_code == query.get('account_code'))
    
    if query.get('limit'):
      q = q.limit(query.get('limit'))
    
    if query.get('offset'):
      q = q.offset(query.get('offset'))
    
    result = await session.execute(q)
    sql_accounts = result.scalars().all()
    return [self._convert_sql_account_to_ledger_account(acc) for acc in sql_accounts]
  
  async def query_transfers(self, query: LedgerQuery, with_balance: bool = True) -> List[LedgerAccountTransfer]:
    """Query transfers by various fields."""
    session = self.get_session()
    
    q = select(SQLAccountTransaction)
    
    if query.get('transfer_id'):
      transfer_id = _ulid_bytes(query.get('transfer_id'))
      if transfer_id is not None:
        q = q.filter(SQLAccountTransaction.id == transfer_id)
    
    if query.get('account_id'):
      account_id = _ulid_bytes(query.get('account_id'))
      if account_id is not None:
        q = q.filter(
          (SQLAccountTransaction.src_id == account_id) |
          (SQLAccountTransaction.dst_id == account_id)
        )
    
    if query.get('transaction_id'):
      transaction_id = _ulid_bytes(query.get('transaction_id'))
      if transaction_id is not None:
        q = q.filter(SQLAccountTransaction.transaction_id == transaction_id)
    
    if query.get('timestamp_min'):
      q = q.filter(SQLAccountTransaction.ts_created >= query.get('timestamp_min'))
    
    if query.get('timestamp_max'):
      q = q.filter(SQLAccountTransaction.ts_created <= query.get('timestamp_max'))
    
    if query.get('limit'):
      q = q.limit(query.get('limit'))
    
    if query.get('offset'):
      q = q.offset(query.get('offset'))
    
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
    
    q = select(SQLTransaction).options(
        selectinload(SQLTransaction.journal_entries),
        selectinload(SQLTransaction.account_transactions)
    )
    
    if query.get('transaction_id'):
      transaction_id = _ulid_bytes(query.get('transaction_id'))
      if transaction_id is not None:
        q = q.filter(SQLTransaction.id == transaction_id)
    
    tt = query.get('transaction_type')
    if tt is not None:
      q = q.filter(SQLTransaction.transaction_type == tt.value)
    
    if query.get('user_id'):
      user_id_raw = query.get('user_id')
      user_id = _ulid_bytes(user_id_raw) if isinstance(user_id_raw, (str, bytes)) else user_id_raw
      q = q.filter(SQLTransaction.user_id == user_id)
    
    if query.get('timestamp_min'):
      q = q.filter(SQLTransaction.ts_created >= query.get('timestamp_min'))
    
    if query.get('timestamp_max'):
      q = q.filter(SQLTransaction.ts_created <= query.get('timestamp_max'))
    
    if query.get('limit'):
      q = q.limit(query.get('limit'))
    
    if query.get('offset'):
      q = q.offset(query.get('offset'))
    
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
      entry_id = _ulid_bytes(query.get('entry_id'))
      if entry_id is not None:
        q = q.filter(SQLJournalEntry.id == entry_id)
    
    if query.get('account_id'):
      account_id = _ulid_bytes(query.get('account_id'))
      if account_id is not None:
        q = q.filter(SQLJournalEntry.account_id == account_id)
    
    if query.get('transaction_id'):
      transaction_id = _ulid_bytes(query.get('transaction_id'))
      if transaction_id is not None:
        q = q.filter(SQLJournalEntry.transaction_id == transaction_id)
    
    if query.get('timestamp_min'):
      q = q.filter(SQLJournalEntry.ts_created >= query.get('timestamp_min'))
    
    if query.get('timestamp_max'):
      q = q.filter(SQLJournalEntry.ts_created <= query.get('timestamp_max'))
    
    if query.get('limit'):
      q = q.limit(query.get('limit'))
    
    if query.get('offset'):
      q = q.offset(query.get('offset'))
    
    result = await session.execute(q)
    sql_entries = result.scalars().all()
    return [self._convert_sql_entry_to_ledger_entry(entry) for entry in sql_entries]
  
  def _convert_sql_account_to_ledger_account(self, sql_account: SQLAccount) -> LedgerAccount:
    """Convert SQLAccount model to LedgerAccount pydantic model."""
    details_raw: Optional[str] = sql_account.details  # type: ignore[assignment]
    return LedgerAccount(  # type: ignore[call-arg]
      id=sql_account.id,  # type: ignore[arg-type]
      name=sql_account.name,  # type: ignore[arg-type]
      account_code=sql_account.account_code,  # type: ignore[arg-type]
      account_type=AccountType(sql_account.account_type),
      side=LedgerSide(sql_account.side),
      workspace_id=sql_account.workspace_id,  # type: ignore[arg-type]
      is_promo=sql_account.is_promo,  # type: ignore[arg-type]
      decimals=sql_account.decimals,  # type: ignore[arg-type]
      currency=sql_account.currency,  # type: ignore[arg-type]
      details=json.loads(details_raw) if details_raw else None,
      history=sql_account.history,  # type: ignore[arg-type]
      allow_negative=True,
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
    if include_transfers and sql_transaction.account_transactions:
      for transfer in sql_transaction.account_transactions:
        converted_transfer = self._convert_sql_account_transaction_to_ledger_transfer(transfer)
        transfers.append(converted_transfer)
    
    details_raw: Optional[str] = sql_transaction.details  # type: ignore[assignment]
    return LedgerTransaction(  # type: ignore[call-arg]
      id=sql_transaction.id,  # type: ignore[arg-type]
      transaction_type=TransactionType(sql_transaction.transaction_type),
      entries=entries,
      transfers=transfers,
      ts_created=sql_transaction.ts_created,  # type: ignore[arg-type]
      user_id=sql_transaction.user_id,  # type: ignore[arg-type]
      reference=sql_transaction.reference,  # type: ignore[arg-type]
      description=sql_transaction.description,  # type: ignore[arg-type]
      details=json.loads(details_raw) if details_raw else None,
    )
  
  def _convert_sql_entry_to_ledger_entry(self, sql_entry: SQLJournalEntry) -> LedgerJournalEntry:
    """Convert SQLJournalEntry model to LedgerJournalEntry pydantic model."""
    tx_id_raw: Optional[bytes] = sql_entry.transaction_id  # type: ignore[assignment]
    return LedgerJournalEntry(  # type: ignore[call-arg]
      id=sql_entry.id,  # type: ignore[arg-type]
      account_id=sql_entry.account_id,  # type: ignore[arg-type]
      debit=sql_entry.debit,  # type: ignore[arg-type]
      credit=sql_entry.credit,  # type: ignore[arg-type]
      ts_created=sql_entry.ts_created,  # type: ignore[arg-type]
      transaction_id=tx_id_raw if tx_id_raw else None,
      description=sql_entry.description,  # type: ignore[arg-type]
    )
  
  def _convert_sql_balance_to_ledger_balance(self, sql_balance: SQLAccountBalance) -> LedgerAccountBalance:
    """Convert SQLAccountBalance model to LedgerAccountBalance pydantic model."""
    this_tx_raw: Optional[bytes] = sql_balance.this_tx  # type: ignore[assignment]
    return LedgerAccountBalance(  # type: ignore[call-arg]
      account_id=sql_balance.account_id,  # type: ignore[arg-type]
      balance=sql_balance.balance,  # type: ignore[arg-type]
      ts_created=sql_balance.ts_created,  # type: ignore[arg-type]
      last_transaction_id=this_tx_raw if this_tx_raw else None,
    )
  
  def get_session(self) -> AsyncSession:
    """Get the current database session."""
    if self._session is None:
      if self._external_session:
        raise RuntimeError("External session not available")
      else:
        raise RuntimeError("No active transaction")
    return self._session
  
  async def close_session(self) -> None:
    """Close the current database session."""
    if self._session is not None:
      if not self._external_session:
        await self._session.close()
      self._session = None
  
  async def close(self) -> None:
    """Close the database engine and any active sessions."""
    # Close active session first
    if self._session is not None:
      if not self._external_session:
        try:
          # Close session gracefully
          await self._session.close()
        except Exception as e:
          print(f"Warning: Error closing session: {e}")
      self._session = None
    
    # Dispose of engine with timeout
    if self.engine is not None:
      try:
        await self.engine.dispose()
      except Exception as e:
        print(f"Warning: Error disposing engine: {e}")
  
  async def get_account_balance(self, account_id: Union[int, str, bytes]) -> int:
    """Get current balance for an account."""
    session = self.get_session()
    aid = _ulid_bytes(account_id)
    if aid is None:
      return 0
    result = await session.execute(select(SQLAccount).filter(SQLAccount.id == aid))
    account = result.scalars().first()
    return account.balance if account else 0  # type: ignore[return-value]
  
  async def create_tables(self) -> None:
    """Create all database tables."""
    assert self.engine is not None, "Engine not initialized"
    async with self.engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)
  

  def _convert_sql_account_transaction_to_ledger_transfer(self, sql_transaction: SQLAccountTransaction, with_balance: bool = True) -> LedgerAccountTransfer:
    """Convert SQLAccountTransaction model to LedgerAccountTransfer pydantic model."""
    tx_id_raw: Optional[bytes] = sql_transaction.transaction_id  # type: ignore[assignment]
    transfer_obj = LedgerAccountTransfer(  # type: ignore[call-arg]
      id=sql_transaction.id,  # type: ignore[arg-type]
      debit_account_id=sql_transaction.dst_id,  # type: ignore[arg-type]
      credit_account_id=sql_transaction.src_id,  # type: ignore[arg-type]
      amount=sql_transaction.amount,  # type: ignore[arg-type]
      ts_created=sql_transaction.ts_created,  # type: ignore[arg-type]
      transaction_id=tx_id_raw if tx_id_raw else None,
    )
    if with_balance:
      # For now, we'll set balance to None since we don't have the balance lookup logic
      # This could be enhanced later to fetch the actual balance
      transfer_obj.balance = None
    return transfer_obj

  async def _create_sqlite_triggers(self) -> None:
    """Create SQLite triggers for balance updates."""
    print("Creating SQLite triggers (async)...")
    assert self.engine is not None, "Engine not initialized"

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

