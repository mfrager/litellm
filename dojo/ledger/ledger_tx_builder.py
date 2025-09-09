"""
Ledger API-Compatible Transaction Builder

This builder outputs transactions in the format required by ledger_api.py, supporting multi-entity, double-entry accounting with strict decimal precision.
"""

from ulid import ULID
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Union, Optional

from .ledger_api import (
  LedgerJournalEntry,
  LedgerTransfer,
  LedgerTransaction,
  TransactionType,
)

__all__ = ["LedgerTransactionBuilder"]

# Helper for scaling decimals
DECIMALS = 6
SCALE = Decimal(10) ** DECIMALS

def to_micro_units(amount: Union[int, float, str, Decimal]) -> int:
  return int((Decimal(str(amount)) * SCALE).to_integral_value())

class LedgerTransactionBuilder:
  def __init__(self, account_ids: Dict[str, str]):
    self.account_ids = account_ids

  def _generate_transfers(self, entries: List[LedgerJournalEntry]) -> List[LedgerTransfer]:
    """Generate transfers from journal entries (debits to credits, splitting as needed) without modifying the original entries."""
    transfers = []
    # Build lists of (index, amount) for debits and credits
    debit_list = [(i, e.debit) for i, e in enumerate(entries) if e.debit and e.debit > 0]
    credit_list = [(i, e.credit) for i, e in enumerate(entries) if e.credit and e.credit > 0]
    debit_idx, credit_idx = 0, 0
    while debit_idx < len(debit_list) and credit_idx < len(credit_list):
      d_i, d_amt = debit_list[debit_idx]
      c_i, c_amt = credit_list[credit_idx]
      transfer_amt = min(d_amt, c_amt)
      transfers.append(LedgerTransfer(
        id=str(ULID()),
        debit_account_id=entries[d_i].account_id,
        credit_account_id=entries[c_i].account_id,
        amount=transfer_amt,
        transaction_id=None,
        balance=None
      ))
      # Update local amounts
      d_amt -= transfer_amt
      c_amt -= transfer_amt
      if d_amt == 0:
        debit_idx += 1
      else:
        debit_list[debit_idx] = (d_i, d_amt)
      if c_amt == 0:
        credit_idx += 1
      else:
        credit_list[credit_idx] = (c_i, c_amt)
    return transfers

  async def payment(self, *, amount, user_id, name: Optional[str] = None, description: Optional[str] = None) -> LedgerTransaction:
    amt = to_micro_units(amount)
    entries = [
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["ar_processor"],
        debit=amt,
        credit=0,
        transaction_id=None,
        description="Pending receipt from processor"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["unearned_revenue"],
        debit=0,
        credit=amt,
        transaction_id=None,
        description="Revenue not yet earned"
      ),
    ]
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.PAYMENT,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or f"Payment authorization for {user_id}",
      details=None
    )

  async def purchase(self, *, user_id, product_amounts: Dict[str, Union[int, float, str, Decimal]], name: Optional[str] = None, description: Optional[str] = None) -> LedgerTransaction:
    entries = []
    total = sum(Decimal(str(amt)) for amt in product_amounts.values())
    total_amt = to_micro_units(total)
    entries.append(
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["unearned_revenue"],
        debit=total_amt,
        credit=0,
        transaction_id=None,
        description="Reduce liability after delivery"
      )
    )
    for product, amount in product_amounts.items():
      code = f"revenue_{product.lower().replace(' ', '_')}"
      amt = to_micro_units(amount)
      entries.append(
        LedgerJournalEntry(
          id=str(ULID()),
          account_id=self.account_ids[code],
          debit=0,
          credit=amt,
          transaction_id=None,
          description=f"Revenue from {product}"
        )
      )
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.PURCHASE,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or f"Revenue recognition for {user_id}",
      details=None
    )

  async def settlement(self, *, amount, name: Optional[str] = None, description: Optional[str] = None, user_id: int = 100) -> LedgerTransaction:
    amt = to_micro_units(amount)
    entries = [
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["cash_bank"],
        debit=amt,
        credit=0,
        transaction_id=None,
        description="Funds from processor"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["ar_processor"],
        debit=0,
        credit=amt,
        transaction_id=None,
        description="Clear pending receivable"
      ),
    ]
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.SETTLEMENT,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or "Settlement from processor",
      details=None
    )

  async def expense(self, *, amount, expense_type: str = "service_fees", name: Optional[str] = None, description: Optional[str] = None, user_id: int = 100) -> LedgerTransaction:
    amt = to_micro_units(amount)
    code = f"{expense_type.lower()}_expense"
    entries = [
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids[code],
        debit=amt,
        credit=0,
        transaction_id=None,
        description=f"Cost of {expense_type.lower()}"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["cash_bank"],
        debit=0,
        credit=amt,
        transaction_id=None,
        description="Funds paid to provider"
      ),
    ]
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.EXPENSE,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or f"{expense_type} expense",
      details=None
    )

  async def tax_collection(self, *, revenue_amount, tax_amount, product: str = "product_a", name: Optional[str] = None, description: Optional[str] = None, user_id: int = 200) -> LedgerTransaction:
    rev_amt = to_micro_units(revenue_amount)
    tax_amt = to_micro_units(tax_amount)
    entries = [
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["cash_bank"],
        debit=rev_amt + tax_amt,
        credit=0,
        transaction_id=None,
        description="Funds from customer"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids[f"revenue_{product.lower()}"] ,
        debit=0,
        credit=rev_amt,
        transaction_id=None,
        description="Product revenue"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["tax_payable"],
        debit=0,
        credit=tax_amt,
        transaction_id=None,
        description="Tax collected"
      ),
    ]
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.TAX,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or f"Tax collection for {product}",
      details=None
    )

  async def tax_remit(self, *, amount, name: Optional[str] = None, description: Optional[str] = None, user_id: int = 100) -> LedgerTransaction:
    amt = to_micro_units(amount)
    entries = [
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["tax_payable"],
        debit=amt,
        credit=0,
        transaction_id=None,
        description="Reduce tax liability"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["cash_bank"],
        debit=0,
        credit=amt,
        transaction_id=None,
        description="Pay tax authority"
      ),
    ]
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.TAX_REMIT,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or "Tax remittance",
      details=None
    )

  async def promo_issue(self, *, amount, user_id, name: Optional[str] = None, description: Optional[str] = None) -> LedgerTransaction:
    amt = to_micro_units(amount)
    entries = [
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["promo_expense"],
        debit=amt,
        credit=0,
        transaction_id=None,
        description="Promo credit cost"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["promo_liability"],
        debit=0,
        credit=amt,
        transaction_id=None,
        description="Promo obligation"
      ),
    ]
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.PROMO,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or f"Issue promo credit to {user_id}",
      details=None
    )

  async def promo_use(self, *, amount, user_id, product: str = "product_a", name: Optional[str] = None, description: Optional[str] = None) -> LedgerTransaction:
    amt = to_micro_units(amount)
    code = f"promo_revenue_{product.lower()}"
    entries = [
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["promo_liability"],
        debit=amt,
        credit=0,
        transaction_id=None,
        description="Reduce promo liability"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids[code],
        debit=0,
        credit=amt,
        transaction_id=None,
        description="Recognize promo revenue"
      ),
    ]
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.USE_PROMO,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or f"Use promo credit for {product}",
      details=None
    )

  async def promo_cancel(self, *, amount, user_id, name: Optional[str] = None, description: Optional[str] = None) -> LedgerTransaction:
    amt = to_micro_units(amount)
    entries = [
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["promo_liability"],
        debit=amt,
        credit=0,
        transaction_id=None,
        description="Remove promo obligation"
      ),
      LedgerJournalEntry(
        id=str(ULID()),
        account_id=self.account_ids["promo_expense"],
        debit=0,
        credit=amt,
        transaction_id=None,
        description="Reverse promo cost"
      ),
    ]
    transfers = self._generate_transfers(entries)
    return LedgerTransaction(
      id=str(ULID()),
      transaction_type=TransactionType.CANCEL_PROMO,
      entries=entries,
      transfers=transfers,
      user_id=user_id,
      reference=name,
      description=description or f"Cancel promo credit for {user_id}",
      details=None
    )

  async def set_transaction_id(self, transaction: LedgerTransaction, transaction_id: str) -> LedgerTransaction:
    """
    Set the transaction ID on the main transaction and all its journal entries and transfers.
    
    Args:
      transaction: The LedgerTransaction to update
      transaction_id: The transaction ID to set
      
    Returns:
      The updated LedgerTransaction with all IDs set
    """
    # Set the main transaction ID
    transaction.id = transaction_id
    
    # Set transaction_id on all journal entries
    if transaction.entries:
      for entry in transaction.entries:
        entry.transaction_id = transaction_id
    
    # Set transaction_id on all transfers
    if transaction.transfers:
      for transfer in transaction.transfers:
        transfer.transaction_id = transaction_id
    
    return transaction 
