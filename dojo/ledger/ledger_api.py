from abc import ABC, abstractmethod
from typing import List, Optional, Union, TypedDict
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import re

class LedgerSide(Enum):
    DEBIT = "debit"
    CREDIT = "credit"

class AccountType(Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"

class TransactionType(Enum):
    PAYMENT = "PAYMENT"
    PURCHASE = "PURCHASE"
    SETTLEMENT = "SETTLEMENT"
    EXPENSE = "EXPENSE"
    TAX = "TAX"
    TAX_REMIT = "TAX_REMIT"
    REFUND = "REFUND"
    PROMO = "PROMO"
    USE_PROMO = "USE_PROMO"
    CANCEL_PROMO = "CANCEL_PROMO"

class LedgerAccount(BaseModel):
    id: Union[int, str, bytes] = Field(..., description="Account ID")
    name: str = Field(..., description="Account name")
    account_code: str = Field(..., description="Unique account code")
    account_type: AccountType = Field(..., description="Account type")
    side: LedgerSide = Field(..., description="Account Side")
    workspace_id: Optional[Union[int, str, bytes]] = Field(default=None, description="Account Workspace ID")
    is_promo: bool = Field(False, description="Promo")
    decimals: int = Field(10, description="Decimals")
    currency: str = Field("USD", description="Currency")
    details: Optional[dict] = Field(default=None, description="Account details")
    history: bool = Field(True, description="Account history")
    allow_negative: bool = Field(True, description="Allow a negative balance")
    external_id: Optional[Union[int, str]] = Field(default=None, description="External ID")

class LedgerAccountBalance(BaseModel):
    account_id: Union[int, str, bytes] = Field(..., description="Account ID")
    balance: int = Field(..., description="Balance")
    ts_created: Optional[datetime] = Field(default=None, description="Balance timestamp")
    last_transaction_id: Optional[Union[int, str, bytes]] = Field(default=None, description="Last transaction ID")

class LedgerAccountTransfer(BaseModel):
    id: Union[int, str, bytes] = Field(..., description="Transfer ID")
    debit_account_id: Union[int, str, bytes] = Field(..., description="Debit account ID")
    credit_account_id: Union[int, str, bytes] = Field(..., description="Credit account ID")
    amount: int = Field(..., description="Transfer amount")
    ts_created: Optional[datetime] = Field(default=None, description="Transfer timestamp")
    transaction_id: Optional[Union[int, str, bytes]] = Field(default=None, description="Transaction ID")
    balance: Optional[LedgerAccountBalance] = Field(default=None, description="Associated account balance after this transfer")

class LedgerJournalEntry(BaseModel):
    id: Union[int, str, bytes] = Field(..., description="Journal entry ID")
    account_id: Union[int, str, bytes] = Field(..., description="Account ID")
    debit: Optional[int] = Field(default=None, description="Debit amount")
    credit: Optional[int] = Field(default=None, description="Credit amount")
    ts_created: Optional[datetime] = Field(default=None, description="Journal entry timestamp")
    transaction_id: Optional[Union[int, str, bytes]] = Field(default=None, description="Transaction ID")
    description: Optional[str] = Field(default=None, description="Journal entry description")

class LedgerTransaction(BaseModel):
    id: Union[int, str, bytes] = Field(..., description="Transaction ID")
    transaction_type: TransactionType = Field(..., description="Transaction type")
    entries: Optional[List[LedgerJournalEntry]] = Field(default=None, description="Journal entries")
    transfers: List[LedgerAccountTransfer] = Field(..., description="Transfers")
    ts_created: Optional[datetime] = Field(default=None, description="Transaction timestamp")
    user_id: Optional[Union[int, str, bytes]] = Field(default=None, description="User ID")
    reference: Optional[str] = Field(default=None, description="Transaction reference")
    description: Optional[str] = Field(default=None, description="Transaction description")
    details: Optional[dict] = Field(default=None, description="Transaction details")

class LedgerAccountTransaction(BaseModel):
    accounts: List[LedgerAccount] = Field(..., description="Accounts")
    
class LedgerTransferTransaction(BaseModel):
    transfers: List[LedgerAccountTransfer] = Field(..., description="Transfers")

class LedgerLogicalTransaction(BaseModel):
    transactions: List[LedgerTransaction] = Field(..., description="Transactions")

class LedgerJournalTransaction(BaseModel):
    entries: List[LedgerJournalEntry] = Field(..., description="Journal entries")

class Ledger(BaseModel):
    id: int = Field(..., description="Ledger ID")
    accounts: List[LedgerAccount] = Field(..., description="Accounts")
    has_journal: bool = Field(True, description="Has journal")
    has_transactions: bool = Field(True, description="Has transactions")
    config: Optional[dict] = Field(default=None, description="Config")

class LedgerAccountFilter(TypedDict, total=False):
    account_id: Optional[Union[int, str, bytes]]
    transaction_id: Optional[Union[int, str, bytes]]
    timestamp_min: Optional[datetime]
    timestamp_max: Optional[datetime]
    limit: Optional[int]
    offset: Optional[int]
    data_param: Optional[dict]

class LedgerQuery(TypedDict, total=False):
    account_id: Optional[Union[int, str, bytes]]
    transfer_id: Optional[Union[int, str, bytes]]
    transaction_id: Optional[Union[int, str, bytes]]
    entry_id: Optional[Union[int, str, bytes]]
    transaction_type: Optional[TransactionType]
    timestamp_min: Optional[datetime]
    timestamp_max: Optional[datetime]
    limit: Optional[int]
    offset: Optional[int]
    data_param: Optional[dict]
    workspace_id: Optional[Union[int, str, bytes]]
    name: Optional[str]
    account_code: Optional[str]
    user_id: Optional[Union[int, str, bytes]]

class LedgerAPI(ABC):
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    @abstractmethod
    async def begin_transaction(self) -> None:
        pass

    @abstractmethod
    async def end_transaction(self) -> None:
        pass

    @abstractmethod
    async def create_accounts(self, account_list: List[LedgerAccountTransaction]) -> None:
        pass

    async def create_transactions(self, tx_list: List[LedgerLogicalTransaction]) -> None:
        pass

    @abstractmethod
    async def create_journal_entries(self, entry_list: List[LedgerJournalTransaction]) -> None:
        pass

    @abstractmethod
    async def create_transfers(self, transfer_list: List[LedgerTransferTransaction]) -> None:
        pass

    @abstractmethod
    async def lookup_accounts(self, account_ids: List[Union[int, str, bytes]]) -> List[LedgerAccount]:
        """
        Fetch accounts by ID:
        - account_ids: List[Union[int, str, bytes]]
        """
        pass

    @abstractmethod
    async def lookup_transfers(self, transfer_ids: List[Union[int, str, bytes]]) -> List[LedgerAccountTransfer]:
        """
        Fetch transfers by ID:
        - transfer_ids: List[Union[int, str, bytes]]
        """
        pass

    @abstractmethod
    async def lookup_transactions(self, transaction_ids: List[Union[int, str, bytes]], journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
        """
        Fetch transactions by ID:
        - transaction_ids: List[Union[int, str, bytes]]
        """
        pass

    @abstractmethod
    async def lookup_entries(self, entry_ids: List[Union[int, str, bytes]]) -> List[LedgerJournalEntry]:
        """
        Fetch journal entries by ID:
        - entry_ids: List[Union[int, str, bytes]]
        """
        pass

    @abstractmethod
    async def get_account_transfers(self, filter: LedgerAccountFilter) -> List[LedgerAccountTransfer]:
        """
        Fetch transfers involving a specific account using an account filter.
        """
        pass

    @abstractmethod
    async def get_account_balances(self, filter: LedgerAccountFilter) -> List[LedgerAccountBalance]:
        """
        Fetch historical balances for an account using an account filter.
        """
        pass

    @abstractmethod
    async def query_accounts(self, query: LedgerQuery) -> List[LedgerAccount]:
        """
        Query accounts by various fields.
        """
        pass

    @abstractmethod
    async def query_transfers(self, query: LedgerQuery) -> List[LedgerAccountTransfer]:
        """
        Query transfers by various fields.
        """
        pass

    @abstractmethod
    async def query_transactions(self, query: LedgerQuery, journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
        """
        Query transactions by various fields.
        """
        pass

    @abstractmethod
    async def query_journal(self, query: LedgerQuery) -> List[LedgerJournalEntry]:
        """
        Query journal entries by various fields.
        """
        pass

def generate_account_code(name: str, workspace_id: Optional[int] = None) -> str:
    """Generate a unique account code from account name and workspace_id."""
    # Convert to lowercase and replace spaces/special chars with underscores
    code = re.sub(r'[^a-zA-Z0-9\s]', '', name.lower())
    code = re.sub(r'\s+', '_', code.strip())
    
    # Add prefix based on workspace_id
    if workspace_id is None or workspace_id == 100:  # Company accounts
        return f"internal_{code}"
    else:  # User accounts
        return f"user_{workspace_id}_{code}"
