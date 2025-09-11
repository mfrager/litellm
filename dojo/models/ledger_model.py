"""
SQL Ledger Schema
"""

import uuid
import json
from ulid import ULID
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional, Union, Dict, Any
from sqlalchemy import Column, Integer, String, Text, Boolean, BigInteger, DateTime, LargeBinary, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from .functions import generate_ulid, generate_utcnow
from .base import Base
from .common import CommonBase


class SQLAccount(CommonBase, Base):
  """SQLAlchemy model for ledger accounts"""
  __tablename__ = 'ledger_accounts'
  
  id = Column(String(26), primary_key=True, default=generate_ulid)
  name = Column(String(255), nullable=False)
  account_type = Column(String(32), nullable=False)     # AccountType enum
  side = Column(String(16), nullable=False)             # LedgerSide enum
  owner_id = Column(String(26), nullable=True)
  is_promo = Column(Boolean, default=False)
  decimals = Column(Integer, default=2)
  currency = Column(String(8), default='USD')
  details = Column(Text, nullable=True)                 # JSON string
  history = Column(Boolean, default=True)
  balance = Column(BigInteger, default=0)               # Current balance
  last_tx = Column(String(26), nullable=True)           # Last transaction ID

  # Indexes for optimal query performance
  __table_args__ = (
    # Index for owner_id queries (very common pattern)
    Index('idx_accounts_owner_id', 'owner_id'),
    
    # Index for last transaction tracking
    Index('idx_accounts_last_tx', 'last_tx'),
    
    # Index for temporal queries
    Index('idx_accounts_updated_at', 'ts_updated'),
    Index('idx_accounts_created_at', 'ts_created'),
  )


class SQLAccountBalance(Base):
  """SQLAlchemy model for account balance history (populated by triggers)"""
  __tablename__ = 'ledger_account_log'
  
  id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
  account_id = Column(String(26), ForeignKey('ledger_accounts.id'), nullable=False)
  last_tx = Column(String(26), nullable=True)                         # Previous transaction ID
  last_balance = Column(BigInteger, nullable=False)                   # Previous balance
  this_tx = Column(String(26), nullable=True)                         # Current transaction ID
  balance = Column(BigInteger, nullable=False)                        # Current balance
  ts_created = Column(DateTime, server_default=func.now())

  # Indexes for optimal query performance
  __table_args__ = (
    # Composite index for account + timestamp (very common for balance history)
    Index('idx_balance_account_ts', 'account_id', 'ts_created'),
    
    # Index for timestamp range queries
    Index('idx_balance_ts', 'ts_created'),
    
    # Index for transaction tracking
    Index('idx_balance_this_tx', 'this_tx'),
    Index('idx_balance_last_tx', 'last_tx'),
  )


class SQLAccountTransaction(Base):
  """SQLAlchemy model for account transactions (triggers balance updates)"""
  __tablename__ = 'ledger_account_transaction'
  
  id = Column(String(26), primary_key=True)
  src_id = Column(String(26), ForeignKey('ledger_accounts.id'), nullable=False)   # Source (credit) account
  dst_id = Column(String(26), ForeignKey('ledger_accounts.id'), nullable=False)   # Destination (debit) account
  amount = Column(BigInteger, nullable=False)                                     # Transfer amount
  ts_created = Column(DateTime, default=generate_utcnow, nullable=False)
  transaction_id = Column(String(26), ForeignKey('ledger_transactions.id'), nullable=True)
  description = Column(Text, nullable=True)

  # Indexes for optimal query performance
  __table_args__ = (
    # Composite indexes for account + timestamp (common for account activity)
    Index('idx_acct_txn_src_ts', 'src_id', 'ts_created'),
    Index('idx_acct_txn_dst_ts', 'dst_id', 'ts_created'),
    
    # Index for transaction grouping
    Index('idx_acct_txn_transaction_id', 'transaction_id'),
    
    # Index for temporal queries
    Index('idx_acct_txn_ts', 'ts_created'),
  )


class SQLJournalEntry(Base):
  """SQLAlchemy model for journal entries"""
  __tablename__ = 'ledger_journal_entries'
  
  id = Column(String(26), primary_key=True)
  account_id = Column(String(26), ForeignKey('ledger_accounts.id'), nullable=False)
  debit = Column(BigInteger, nullable=True)
  credit = Column(BigInteger, nullable=True)
  transaction_id = Column(String(26), ForeignKey('ledger_transactions.id'), nullable=True)
  description = Column(Text, nullable=True)
  ts_created = Column(DateTime, default=generate_utcnow, nullable=False)

  # Indexes for optimal query performance
  __table_args__ = (
    # Primary index for account-based journal queries
    Index('idx_journal_account_id', 'account_id'),
    
    # Index for transaction grouping
    Index('idx_journal_transaction_id', 'transaction_id'),
    
    # Index for timestamp queries
    Index('idx_journal_timestamp', 'ts_created'),
    
    # Composite index for account + timestamp (chronological account activity)
    Index('idx_journal_account_timestamp', 'account_id', 'ts_created'),
  )


class SQLTransaction(Base):
  """SQLAlchemy model for transactions"""
  __tablename__ = 'ledger_transactions'
  
  id = Column(String(26), primary_key=True)
  transaction_type = Column(String(32), nullable=False)   # TransactionType enum
  user_id = Column(String(26), nullable=True)
  reference = Column(String(255), nullable=True)
  description = Column(Text, nullable=True)
  details = Column(Text, nullable=True)                   # JSON string
  ts_created = Column(DateTime, default=generate_utcnow, nullable=False)
  
  # Relationships
  journal_entries = relationship("SQLJournalEntry", backref="transaction")
  account_transactions = relationship("SQLAccountTransaction", backref="transaction")

  # Indexes for optimal query performance
  __table_args__ = (
    # Index for timestamp range queries
    Index('idx_transactions_created_at', 'ts_created'),
    
    # Composite index for user + timestamp (common for user activity)
    Index('idx_transactions_user_timestamp', 'user_id', 'ts_created'),
    
    # Composite index for type + timestamp (common for transaction type analysis)
    Index('idx_transactions_type_timestamp', 'transaction_type', 'ts_created'),
    
    # Index for reference lookups (useful for external system integration)
    Index('idx_transactions_reference', 'reference'),
  )


class SQLLedger(CommonBase, Base):
  """SQLAlchemy model for ledger configuration"""
  __tablename__ = 'ledgers'
  
  id = Column(String(26), primary_key=True, default=generate_ulid)
  config = Column(Text, nullable=True)                # JSON string

  # Indexes for optimal query performance
  __table_args__ = (
    # Index for temporal queries
    Index('idx_ledgers_created_at', 'ts_created'),
    Index('idx_ledgers_updated_at', 'ts_updated'),
  )

