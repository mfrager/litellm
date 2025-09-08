"""
SQL Ledger Backend Implementation

This module provides a SQLAlchemy-based implementation of the LedgerAPI
for storing accounting data in a relational database.
"""

import json
from ulid import ULID
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from typing import List, Optional, Union, Dict, Any

from models.ledger_model import (
  SQLAccount,
  SQLAccountBalance,
  SQLAccountTransaction,
  SQLJournalEntry,
  SQLTransfer,
  SQLTransaction,
  SQLLedger,
)

from .ledger_api import (
  LedgerAPI, 
  Ledger,
  LedgerAccount, 
  LedgerAccountBalance, 
  LedgerJournalEntry, 
  LedgerTransfer, 
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
      database_url: SQLAlchemy database URL (e.g., 'postgresql://user:pass@localhost/db')
    """
    super().__init__(ledger)
    self.engine = create_engine(database_url, echo=False)
    self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    self._session: Optional[Session] = None
    self.database_url = database_url
    
    # Create tables and triggers
    self._setup_database()
  
  def _setup_database(self) -> None:
    """Create tables and database triggers for balance management."""
    # Create tables
    Base.metadata.create_all(bind=self.engine)
    
    # Add triggers based on database type
    self._create_triggers()
  
  def _create_triggers(self) -> None:
    """Create database triggers for automatic balance updates."""
    dialect_name = self.engine.dialect.name.lower()
    
    print(f"Creating triggers for database: {dialect_name}")
    
    if dialect_name == 'mysql':
      self._create_mysql_triggers()
    elif dialect_name in ['postgresql', 'postgres']:
      self._create_postgresql_triggers()
    elif dialect_name == 'sqlite':
      self._create_sqlite_triggers()
    else:
      print(f"Warning: No triggers implemented for database type: {dialect_name}")
  
  def _create_sqlite_triggers(self) -> None:
    """Create SQLite triggers for balance updates."""
    print("Creating SQLite triggers...")
    
    # Create triggers directly using raw SQL
    with self.engine.connect() as connection:
      # Drop existing triggers first
      try:
        connection.execute(text("DROP TRIGGER IF EXISTS tx_transaction_insert"))
        connection.execute(text("DROP TRIGGER IF EXISTS tx_balance_update"))
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
          ts_updated = NEW.ts, 
          last_tx = NEW.id 
        WHERE id = NEW.src_id;
        
        UPDATE ledger_accounts 
        SET balance = balance + NEW.amount, 
          ts_updated = NEW.ts, 
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
        INSERT INTO ledger_account_log (account_id, last_tx, last_balance, this_tx, balance, ts) 
        VALUES (OLD.id, OLD.last_tx, OLD.balance, NEW.last_tx, NEW.balance, datetime('now'));
      END
      """
      
      try:
        connection.execute(text(tx_trigger_sql))
        print("✅ Created transaction trigger")
      except Exception as e:
        print(f"❌ Failed to create transaction trigger: {e}")
      
      try:
        connection.execute(text(balance_trigger_sql))
        print("✅ Created balance logging trigger")
      except Exception as e:
        print(f"❌ Failed to create balance logging trigger: {e}")
      
      connection.commit()
    
    print("SQLite triggers creation completed.")
  
  def _create_mysql_triggers(self) -> None:
    """Create MySQL triggers for balance updates."""
    print("Creating MySQL triggers...")
    
    # Create triggers directly using raw SQL
    with self.engine.connect() as connection:
      # Drop existing triggers first
      try:
        connection.execute(text("DROP TRIGGER IF EXISTS tx_transaction_insert"))
        connection.execute(text("DROP TRIGGER IF EXISTS tx_balance_update"))
      except Exception as e:
        print(f"Note: Could not drop existing triggers: {e}")
      
      # MySQL trigger syntax
      tx_trigger_sql = """
      CREATE TRIGGER tx_transaction_insert 
      AFTER INSERT ON ledger_account_transaction 
      FOR EACH ROW 
      BEGIN
        UPDATE ledger_accounts 
        SET balance = balance - NEW.amount, 
          ts_updated = NEW.ts, 
          last_tx = NEW.id 
        WHERE id = NEW.src_id;
        
        UPDATE ledger_accounts 
        SET balance = balance + NEW.amount, 
          ts_updated = NEW.ts, 
          last_tx = NEW.id 
        WHERE id = NEW.dst_id;
      END
      """
      
      balance_trigger_sql = """
      CREATE TRIGGER tx_balance_update 
      AFTER UPDATE ON ledger_accounts 
      FOR EACH ROW 
      BEGIN
        IF OLD.balance != NEW.balance THEN
          INSERT INTO ledger_account_log (account_id, last_tx, last_balance, this_tx, balance, ts) 
          VALUES (OLD.id, OLD.last_tx, OLD.balance, NEW.last_tx, NEW.balance, UTC_TIMESTAMP());
        END IF;
      END
      """
      
      try:
        connection.execute(text(tx_trigger_sql))
        print("✅ Created transaction trigger")
      except Exception as e:
        print(f"❌ Failed to create transaction trigger: {e}")
      
      try:
        connection.execute(text(balance_trigger_sql))
        print("✅ Created balance logging trigger")
      except Exception as e:
        print(f"❌ Failed to create balance logging trigger: {e}")
      
      connection.commit()
    
    print("MySQL triggers creation completed.")
  
  def _create_postgresql_triggers(self) -> None:
    """Create PostgreSQL triggers for balance updates."""
    print("Creating PostgreSQL triggers...")
    
    with self.engine.connect() as connection:
      # Drop existing triggers and functions first
      try:
        connection.execute(text("DROP TRIGGER IF EXISTS tx_transaction_insert ON ledger_account_transaction"))
        connection.execute(text("DROP TRIGGER IF EXISTS tx_balance_update ON ledger_accounts"))
        connection.execute(text("DROP FUNCTION IF EXISTS tx_transaction_insert_func()"))
        connection.execute(text("DROP FUNCTION IF EXISTS tx_balance_update_func()"))
      except Exception as e:
        print(f"Note: Could not drop existing triggers: {e}")
      
      # Create functions
      tx_function_sql = """
      CREATE OR REPLACE FUNCTION tx_transaction_insert_func()
      RETURNS TRIGGER AS $$
      BEGIN
        UPDATE ledger_accounts 
        SET balance = balance - NEW.amount, 
          ts_updated = NEW.ts, 
          last_tx = NEW.id 
        WHERE id = NEW.src_id;
        
        UPDATE ledger_accounts 
        SET balance = balance + NEW.amount, 
          ts_updated = NEW.ts, 
          last_tx = NEW.id 
        WHERE id = NEW.dst_id;
        
        RETURN NEW;
      END;
      $$ LANGUAGE plpgsql;
      """
      
      balance_function_sql = """
      CREATE OR REPLACE FUNCTION tx_balance_update_func()
      RETURNS TRIGGER AS $$
      BEGIN
        IF OLD.balance != NEW.balance THEN
          INSERT INTO ledger_account_log (account_id, last_tx, last_balance, this_tx, balance, ts) 
          VALUES (OLD.id, OLD.last_tx, OLD.balance, NEW.last_tx, NEW.balance, NOW());
        END IF;
        
        RETURN NEW;
      END;
      $$ LANGUAGE plpgsql;
      """
      
      # Create triggers
      tx_trigger_sql = """
      CREATE TRIGGER tx_transaction_insert 
      AFTER INSERT ON ledger_account_transaction 
      FOR EACH ROW EXECUTE FUNCTION tx_transaction_insert_func()
      """
      
      balance_trigger_sql = """
      CREATE TRIGGER tx_balance_update 
      AFTER UPDATE ON ledger_accounts 
      FOR EACH ROW EXECUTE FUNCTION tx_balance_update_func()
      """
      
      try:
        connection.execute(text(tx_function_sql))
        connection.execute(text(balance_function_sql))
        connection.execute(text(tx_trigger_sql))
        connection.execute(text(balance_trigger_sql))
        print("✅ Created PostgreSQL triggers and functions")
      except Exception as e:
        print(f"❌ Failed to create PostgreSQL triggers: {e}")
      
      connection.commit()
    
    print("PostgreSQL triggers creation completed.")
  
  def begin_transaction(self) -> None:
    """Begin a database transaction."""
    if self._session is not None:
      raise RuntimeError("Transaction already active")
    
    self._session = self.SessionLocal()
    self._session.begin()
  
  def end_transaction(self) -> None:
    """Commit the current transaction."""
    if self._session is None:
      raise RuntimeError("No active transaction")
    
    try:
      self._session.commit()
    finally:
      self._session.close()
      self._session = None
  
  def cancel_transaction(self) -> None:
    """Rollback the current transaction."""
    if self._session is None:
      raise RuntimeError("No active transaction")
    
    try:
      self._session.rollback()
    finally:
      self._session.close()
      self._session = None
  
  def create_accounts(self, account_list: List[LedgerAccountTransaction]) -> None:
    """Create new ledger accounts."""
    session = self.get_session()
    
    for account_tx in account_list:
      for account in account_tx.accounts:
        # Convert string ID to ULID bytes, or generate new ULID if needed
        account_id_bytes = ensure_ulid_bytes(account.id)
        if account_id_bytes is None:
          account_id_bytes = ULID().bytes
        
        sql_account = SQLAccount(
          id=account_id_bytes,
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
        session.add(sql_account)
    
    session.flush()
  
  def create_journal_entries(self, entry_list: List[LedgerJournalTransaction]) -> None:
    """Create new journal entries."""
    session = self.get_session()
    
    for entry_tx in entry_list:
      for entry in entry_tx.entries:
        # Convert string IDs to ULID bytes
        entry_id_bytes = ensure_ulid_bytes(entry.id)
        if entry_id_bytes is None:
          entry_id_bytes = ULID().bytes
        
        account_id_bytes = ensure_ulid_bytes(entry.account_id)
        transaction_id_bytes = ensure_ulid_bytes(entry.transaction_id) if entry.transaction_id else None
        
        sql_entry = SQLJournalEntry(
          id=entry_id_bytes,
          account_id=account_id_bytes,
          debit=entry.debit,
          credit=entry.credit,
          timestamp=entry.timestamp,
          transaction_id=transaction_id_bytes,
          description=entry.description
        )
        session.add(sql_entry)
    
    session.flush()
  
  def create_transfers(self, transfer_list: List[LedgerTransferTransaction]) -> None:
    """Create new transfers and corresponding account transactions."""
    session = self.get_session()
    
    for transfer_tx in transfer_list:
      for transfer in transfer_tx.transfers:
        # Convert string IDs to ULID bytes
        transfer_id_bytes = ensure_ulid_bytes(transfer.id)
        if transfer_id_bytes is None:
          transfer_id_bytes = ULID().bytes
        
        debit_account_id_bytes = ensure_ulid_bytes(transfer.debit_account_id)
        credit_account_id_bytes = ensure_ulid_bytes(transfer.credit_account_id)
        transaction_id_bytes = ensure_ulid_bytes(transfer.transaction_id) if transfer.transaction_id else None
        
        # Create the transfer record
        sql_transfer = SQLTransfer(
          id=transfer_id_bytes,
          debit_account_id=debit_account_id_bytes,
          credit_account_id=credit_account_id_bytes,
          amount=transfer.amount,
          timestamp=transfer.timestamp,
          transaction_id=transaction_id_bytes
        )
        session.add(sql_transfer)
        
        # Create the account transaction (triggers will update balances)
        account_tx_id_bytes = ULID().bytes
        account_tx = SQLAccountTransaction(
          id=account_tx_id_bytes,
          src_id=credit_account_id_bytes,  # Source is credit account
          dst_id=debit_account_id_bytes,   # Destination is debit account
          amount=transfer.amount,
          ts=datetime.now(timezone.utc),
          transaction_id=transaction_id_bytes,
          description=f"Transfer {bytes_to_ulid(transfer_id_bytes)}"
        )
        session.add(account_tx)
    
    session.flush()
  
  def lookup_accounts(self, account_ids: List[Union[int, str]]) -> List[LedgerAccount]:
    """Fetch accounts by ID."""
    session = self.get_session()
    
    # Convert all IDs to bytes format
    bytes_ids = [ensure_ulid_bytes(str(aid)) for aid in account_ids]
    bytes_ids = [bid for bid in bytes_ids if bid is not None]  # Filter out None values
    
    sql_accounts = session.query(SQLAccount).filter(SQLAccount.id.in_(bytes_ids)).all()
    
    return [self._convert_sql_account_to_ledger_account(acc) for acc in sql_accounts]
  
  def lookup_transfers(self, transfer_ids: List[Union[int, str]], with_balance: bool = True) -> List[LedgerTransfer]:
    """Fetch transfers by ID."""
    session = self.get_session()
    
    # Convert all IDs to bytes format
    bytes_ids = [ensure_ulid_bytes(str(tid)) for tid in transfer_ids]
    bytes_ids = [bid for bid in bytes_ids if bid is not None]  # Filter out None values
    
    sql_transfers = session.query(SQLTransfer).filter(SQLTransfer.id.in_(bytes_ids)).all()
    
    return [self._convert_sql_transfer_to_ledger_transfer(transfer, with_balance=with_balance) for transfer in sql_transfers]
  
  def lookup_transactions(self, transaction_ids: List[Union[int, str]], 
              journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
    """Fetch transactions by ID."""
    session = self.get_session()
    
    # Convert all IDs to bytes format
    bytes_ids = [ensure_ulid_bytes(str(tid)) for tid in transaction_ids]
    bytes_ids = [bid for bid in bytes_ids if bid is not None]  # Filter out None values
    
    sql_transactions = session.query(SQLTransaction).filter(SQLTransaction.id.in_(bytes_ids)).all()
    
    return [self._convert_sql_transaction_to_ledger_transaction(tx, journal, transfers) 
        for tx in sql_transactions]
  
  def lookup_entries(self, entry_ids: List[Union[int, str]]) -> List[LedgerJournalEntry]:
    """Fetch journal entries by ID."""
    session = self.get_session()
    
    # Convert all IDs to bytes format
    bytes_ids = [ensure_ulid_bytes(str(eid)) for eid in entry_ids]
    bytes_ids = [bid for bid in bytes_ids if bid is not None]  # Filter out None values
    
    sql_entries = session.query(SQLJournalEntry).filter(SQLJournalEntry.id.in_(bytes_ids)).all()
    
    return [self._convert_sql_entry_to_ledger_entry(entry) for entry in sql_entries]
  
  def get_account_transfers(self, filter: LedgerAccountFilter, with_balance: bool = True) -> List[LedgerTransfer]:
    """Fetch transfers involving a specific account."""
    session = self.get_session()
    
    query = session.query(SQLTransfer)
    
    if filter.get('account_id'):
      account_id_bytes = ensure_ulid_bytes(str(filter['account_id']))
      if account_id_bytes:
        query = query.filter(
          (SQLTransfer.debit_account_id == account_id_bytes) | 
          (SQLTransfer.credit_account_id == account_id_bytes)
        )
    
    if filter.get('timestamp_min'):
      query = query.filter(SQLTransfer.timestamp >= filter['timestamp_min'])
    
    if filter.get('timestamp_max'):
      query = query.filter(SQLTransfer.timestamp <= filter['timestamp_max'])
    
    if filter.get('limit'):
      query = query.limit(filter['limit'])
    
    if filter.get('offset'):
      query = query.offset(filter['offset'])
    
    sql_transfers = query.all()
    return [self._convert_sql_transfer_to_ledger_transfer(transfer, with_balance=with_balance) for transfer in sql_transfers]
  
  def get_account_balances(self, filter: LedgerAccountFilter) -> List[LedgerAccountBalance]:
    """Fetch historical balances for an account."""
    session = self.get_session()
    
    query = session.query(SQLAccountBalance)
    
    if filter.get('account_id'):
      account_id_bytes = ensure_ulid_bytes(str(filter['account_id']))
      if account_id_bytes:
        query = query.filter(SQLAccountBalance.account_id == account_id_bytes)
    
    if filter.get('timestamp_min'):
      # Convert timestamp to datetime for comparison
      min_dt = datetime.fromtimestamp(filter['timestamp_min'])
      query = query.filter(SQLAccountBalance.ts >= min_dt)
    
    if filter.get('timestamp_max'):
      max_dt = datetime.fromtimestamp(filter['timestamp_max'])
      query = query.filter(SQLAccountBalance.ts <= max_dt)
    
    # Order by timestamp (most recent first) BEFORE applying limit/offset
    query = query.order_by(SQLAccountBalance.ts.desc())
    
    if filter.get('limit'):
      query = query.limit(filter['limit'])
    
    if filter.get('offset'):
      query = query.offset(filter['offset'])
    
    sql_balances = query.all()
    
    return [self._convert_sql_balance_to_ledger_balance(balance) for balance in sql_balances]
  
  def query_accounts(self, query: LedgerQuery) -> List[LedgerAccount]:
    """Query accounts by various fields."""
    session = self.get_session()
    
    q = session.query(SQLAccount)
    
    if query.get('account_id'):
      account_id_bytes = ensure_ulid_bytes(str(query['account_id']))
      if account_id_bytes:
        q = q.filter(SQLAccount.id == account_id_bytes)
    
    if query.get('owner_id'):
      q = q.filter(SQLAccount.owner_id == query['owner_id'])
    
    if query.get('limit'):
      q = q.limit(query['limit'])
    
    if query.get('offset'):
      q = q.offset(query['offset'])
    
    sql_accounts = q.all()
    return [self._convert_sql_account_to_ledger_account(acc) for acc in sql_accounts]
  
  def query_transfers(self, query: LedgerQuery, with_balance: bool = True) -> List[LedgerTransfer]:
    """Query transfers by various fields."""
    session = self.get_session()
    
    q = session.query(SQLTransfer)
    
    if query.get('transfer_id'):
      transfer_id_bytes = ensure_ulid_bytes(str(query['transfer_id']))
      if transfer_id_bytes:
        q = q.filter(SQLTransfer.id == transfer_id_bytes)
    
    if query.get('account_id'):
      account_id_bytes = ensure_ulid_bytes(str(query['account_id']))
      if account_id_bytes:
        q = q.filter(
          (SQLTransfer.debit_account_id == account_id_bytes) | 
          (SQLTransfer.credit_account_id == account_id_bytes)
        )
    
    if query.get('transaction_id'):
      transaction_id_bytes = ensure_ulid_bytes(str(query['transaction_id']))
      if transaction_id_bytes:
        q = q.filter(SQLTransfer.transaction_id == transaction_id_bytes)
    
    if query.get('timestamp_min'):
      q = q.filter(SQLTransfer.timestamp >= query['timestamp_min'])
    
    if query.get('timestamp_max'):
      q = q.filter(SQLTransfer.timestamp <= query['timestamp_max'])
    
    if query.get('limit'):
      q = q.limit(query['limit'])
    
    if query.get('offset'):
      q = q.offset(query['offset'])
    
    sql_transfers = q.all()
    return [self._convert_sql_transfer_to_ledger_transfer(transfer, with_balance=with_balance) for transfer in sql_transfers]
  
  def query_transactions(self, query: LedgerQuery, 
             journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
    """Query transactions by various fields."""
    session = self.get_session()
    
    q = session.query(SQLTransaction)
    
    if query.get('transaction_id'):
      transaction_id_bytes = ensure_ulid_bytes(str(query['transaction_id']))
      if transaction_id_bytes:
        q = q.filter(SQLTransaction.id == transaction_id_bytes)
    
    if query.get('transaction_type'):
      q = q.filter(SQLTransaction.transaction_type == query['transaction_type'].value)
    
    if query.get('user_id'):
      q = q.filter(SQLTransaction.user_id == query['user_id'])
    
    if query.get('timestamp_min'):
      min_dt = datetime.fromtimestamp(query['timestamp_min'])
      q = q.filter(SQLTransaction.timestamp >= min_dt)
    
    if query.get('timestamp_max'):
      max_dt = datetime.fromtimestamp(query['timestamp_max'])
      q = q.filter(SQLTransaction.timestamp <= max_dt)
    
    if query.get('limit'):
      q = q.limit(query['limit'])
    
    if query.get('offset'):
      q = q.offset(query['offset'])
    
    sql_transactions = q.all()
    return [self._convert_sql_transaction_to_ledger_transaction(tx, journal, transfers) 
        for tx in sql_transactions]
  
  def query_journal(self, query: LedgerQuery) -> List[LedgerJournalEntry]:
    """Query journal entries by various fields."""
    session = self.get_session()
    
    q = session.query(SQLJournalEntry)
    
    if query.get('entry_id'):
      entry_id_bytes = ensure_ulid_bytes(str(query['entry_id']))
      if entry_id_bytes:
        q = q.filter(SQLJournalEntry.id == entry_id_bytes)
    
    if query.get('account_id'):
      account_id_bytes = ensure_ulid_bytes(str(query['account_id']))
      if account_id_bytes:
        q = q.filter(SQLJournalEntry.account_id == account_id_bytes)
    
    if query.get('transaction_id'):
      transaction_id_bytes = ensure_ulid_bytes(str(query['transaction_id']))
      if transaction_id_bytes:
        q = q.filter(SQLJournalEntry.transaction_id == transaction_id_bytes)
    
    if query.get('timestamp_min'):
      q = q.filter(SQLJournalEntry.timestamp >= query['timestamp_min'])
    
    if query.get('timestamp_max'):
      q = q.filter(SQLJournalEntry.timestamp <= query['timestamp_max'])
    
    if query.get('limit'):
      q = q.limit(query['limit'])
    
    if query.get('offset'):
      q = q.offset(query['offset'])
    
    sql_entries = q.all()
    return [self._convert_sql_entry_to_ledger_entry(entry) for entry in sql_entries]
  
  def _convert_sql_account_to_ledger_account(self, sql_account: SQLAccount) -> LedgerAccount:
    """Convert SQLAccount model to LedgerAccount pydantic model."""
    return LedgerAccount(
      id=bytes_to_ulid(sql_account.id),
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
  
  def _convert_sql_transfer_to_ledger_transfer(self, sql_transfer: SQLTransfer, with_balance: bool = True) -> LedgerTransfer:
    """Convert SQLTransfer model to LedgerTransfer pydantic model, optionally attaching the associated balance record."""
    transfer_obj = LedgerTransfer(
      id=bytes_to_ulid(sql_transfer.id),
      debit_account_id=bytes_to_ulid(sql_transfer.debit_account_id),
      credit_account_id=bytes_to_ulid(sql_transfer.credit_account_id),
      amount=sql_transfer.amount,
      timestamp=sql_transfer.timestamp,
      transaction_id=bytes_to_ulid(sql_transfer.transaction_id) if sql_transfer.transaction_id else None
    )
    if with_balance:
      session = self.get_session()
      # Find the balance record for the debit account after this transfer (this_tx == transfer.id)
      balance_record = session.query(SQLAccountBalance).filter(
        SQLAccountBalance.account_id == sql_transfer.debit_account_id,
        SQLAccountBalance.this_tx == sql_transfer.id
      ).first()
      if balance_record:
        transfer_obj.balance = self._convert_sql_balance_to_ledger_balance(balance_record)
    return transfer_obj
  
  def _convert_sql_transaction_to_ledger_transaction(self, sql_transaction: SQLTransaction, 
                           include_journal: bool = True, 
                           include_transfers: bool = True) -> LedgerTransaction:
    """Convert SQLTransaction model to LedgerTransaction pydantic model."""
    entries = None
    if include_journal and sql_transaction.journal_entries:
      entries = [self._convert_sql_entry_to_ledger_entry(entry) 
            for entry in sql_transaction.journal_entries]
    
    transfers = []
    if include_transfers and sql_transaction.transfers:
      transfers = [self._convert_sql_transfer_to_ledger_transfer(transfer) 
            for transfer in sql_transaction.transfers]
    
    return LedgerTransaction(
      id=bytes_to_ulid(sql_transaction.id),
      transaction_type=TransactionType(sql_transaction.transaction_type),
      entries=entries,
      transfers=transfers,
      timestamp=sql_transaction.timestamp,
      user_id=sql_transaction.user_id,
      reference=sql_transaction.reference,
      description=sql_transaction.description,
      details=json.loads(sql_transaction.details) if sql_transaction.details else None
    )
  
  def _convert_sql_entry_to_ledger_entry(self, sql_entry: SQLJournalEntry) -> LedgerJournalEntry:
    """Convert SQLJournalEntry model to LedgerJournalEntry pydantic model."""
    return LedgerJournalEntry(
      id=bytes_to_ulid(sql_entry.id),
      account_id=bytes_to_ulid(sql_entry.account_id),
      debit=sql_entry.debit,
      credit=sql_entry.credit,
      timestamp=sql_entry.timestamp,
      transaction_id=bytes_to_ulid(sql_entry.transaction_id) if sql_entry.transaction_id else None,
      description=sql_entry.description
    )
  
  def _convert_sql_balance_to_ledger_balance(self, sql_balance: SQLAccountBalance) -> LedgerAccountBalance:
    """Convert SQLAccountBalance model to LedgerAccountBalance pydantic model."""
    return LedgerAccountBalance(
      account_id=bytes_to_ulid(sql_balance.account_id),
      balance=sql_balance.balance,
      timestamp=int(sql_balance.ts.timestamp()) if sql_balance.ts else None,
      last_transaction_id=bytes_to_ulid(sql_balance.this_tx) if sql_balance.this_tx else None
    )
  
  def get_session(self) -> Session:
    """Get the current database session."""
    if self._session is None:
      raise RuntimeError("No active transaction")
    return self._session
  
  def close_session(self) -> None:
    """Close the current database session."""
    if self._session is not None:
      self._session.close()
      self._session = None
  
  def get_account_balance(self, account_id: Union[int, str]) -> int:
    """Get current balance for an account."""
    session = self.get_session()
    account_id_bytes = ensure_ulid_bytes(str(account_id))
    if not account_id_bytes:
      return 0
    
    account = session.query(SQLAccount).filter(SQLAccount.id == account_id_bytes).first()
    return account.balance if account else 0 

