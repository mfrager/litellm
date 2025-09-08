from abc import ABC, abstractmethod
from typing import List, Optional, Union, TypedDict
from pydantic import BaseModel, Field
from enum import Enum

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
    id: Union[int, str] = Field(..., description="Account ID")
    name: str = Field(..., description="Account name")
    account_type: AccountType = Field(..., description="Account type")
    side: LedgerSide = Field(..., description="Account Side")
    owner_id: Optional[int] = Field(None, description="Account Owner ID")
    is_promo: bool = Field(False, description="Promo")
    decimals: int = Field(2, description="Decimals")
    currency: str = Field("USD", description="Currency")
    details: Optional[dict] = Field(..., description="Account details")
    history: bool = Field(True, description="Account history")
    allow_negative: bool = Field(True, description="Allow a negative balance")
    external_id: Optional[Union[int, str]] = Field(None, description="External ID")

class LedgerAccountBalance(BaseModel):
    account_id: Union[int, str] = Field(..., description="Account ID")
    balance: int = Field(..., description="Balance")
    ts_created: Optional[int] = Field(..., description="Balance timestamp")
    last_transaction_id: Optional[Union[int, str]] = Field(..., description="Last transaction ID")

class LedgerJournalEntry(BaseModel):
    id: Union[int, str] = Field(..., description="Journal entry ID")
    account_id: Union[int, str] = Field(..., description="Account ID")
    debit: Optional[int] = Field(..., description="Debit amount")
    credit: Optional[int] = Field(..., description="Credit amount")
    ts_created: Optional[int] = Field(None, description="Journal entry timestamp")
    transaction_id: Optional[Union[int, str]] = Field(..., description="Transaction ID")
    description: Optional[str] = Field(..., description="Journal entry description")

class LedgerTransfer(BaseModel):
    id: Union[int, str] = Field(..., description="Transfer ID")
    debit_account_id: Union[int, str] = Field(..., description="Debit account ID")
    credit_account_id: Union[int, str] = Field(..., description="Credit account ID")
    amount: int = Field(..., description="Transfer amount")
    ts_created: Optional[int] = Field(None, description="Transfer timestamp")
    transaction_id: Optional[Union[int, str]] = Field(..., description="Transaction ID")
    balance: Optional[LedgerAccountBalance] = Field(None, description="Associated account balance after this transfer")

class LedgerTransaction(BaseModel):
    id: Union[int, str] = Field(..., description="Transaction ID")
    transaction_type: TransactionType = Field(..., description="Transaction type")
    entries: Optional[List[LedgerJournalEntry]] = Field(..., description="Journal entries")
    transfers: List[LedgerTransfer] = Field(..., description="Transfers")
    ts_created: Optional[int] = Field(None, description="Transaction timestamp")
    user_id: Optional[int] = Field(..., description="User ID")
    reference: Optional[str] = Field(..., description="Transaction reference")
    description: Optional[str] = Field(..., description="Transaction description")
    details: Optional[dict] = Field(..., description="Transaction details")

class LedgerAccountTransaction(BaseModel):
    accounts: List[LedgerAccount] = Field(..., description="Accounts")
    
class LedgerTransferTransaction(BaseModel):
    transfers: List[LedgerTransfer] = Field(..., description="Transfers")

class LedgerLogicalTransaction(BaseModel):
    transactions: List[LedgerTransaction] = Field(..., description="Transactions")

class LedgerJournalTransaction(BaseModel):
    entries: List[LedgerJournalEntry] = Field(..., description="Journal entries")

class Ledger(BaseModel):
    id: int = Field(..., description="Ledger ID")
    accounts: List[LedgerAccount] = Field(..., description="Accounts")
    has_journal: bool = Field(True, description="Has journal")
    has_transactions: bool = Field(True, description="Has transactions")
    config: Optional[dict] = Field(..., description="Config")

class LedgerAccountFilter(TypedDict, total=False):
    account_id: Optional[Union[int, str]]
    transaction_id: Optional[Union[int, str]]
    timestamp_min: Optional[int]
    timestamp_max: Optional[int]
    limit: Optional[int]
    offset: Optional[int]
    data_param: Optional[dict]

class LedgerQuery(TypedDict, total=False):
    account_id: Optional[Union[int, str]]
    transfer_id: Optional[Union[int, str]]
    transaction_id: Optional[Union[int, str]]
    entry_id: Optional[Union[int, str]]
    transaction_type: Optional[TransactionType]
    timestamp_min: Optional[int]
    timestamp_max: Optional[int]
    limit: Optional[int]
    offset: Optional[int]
    data_param: Optional[dict]

class LedgerAPI(ABC):
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    @abstractmethod
    def begin_transaction(self) -> None:
        pass

    @abstractmethod
    def end_transaction(self) -> None:
        pass

    @abstractmethod
    def create_accounts(self, account_list: List[LedgerAccountTransaction]) -> None:
        pass

    def create_transactions(self, tx_list: List[LedgerAccountTransaction]) -> None:
        self.begin_transaction()
        for tx in tx_list:
            if self.ledger.has_journal:
                self.create_journal_entries(tx.entries)
            self.create_transfers(tx.transfers)
        self.end_transaction()

    @abstractmethod
    def create_journal_entries(self, entry_list: List[LedgerJournalTransaction]) -> None:
        pass

    @abstractmethod
    def create_transfers(self, transfer_list: List[LedgerTransferTransaction]) -> None:
        pass

    @abstractmethod
    def lookup_accounts(self, account_ids: List[Union[int, str]]) -> List[LedgerAccount]:
        """
        Fetch accounts by ID:
        - account_ids: List[Union[int, str]]
        """
        pass

    @abstractmethod
    def lookup_transfers(self, transfer_ids: List[Union[int, str]]) -> List[LedgerTransfer]:
        """
        Fetch transfers by ID:
        - transfer_ids: List[Union[int, str]]
        """
        pass

    @abstractmethod
    def lookup_transactions(self, transaction_ids: List[Union[int, str]], journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
        """
        Fetch transactions by ID:
        - transaction_ids: List[Union[int, str]]
        """
        pass

    @abstractmethod
    def lookup_entries(self, entry_ids: List[Union[int, str]]) -> List[LedgerJournalEntry]:
        """
        Fetch journal entries by ID:
        - entry_ids: List[Union[int, str]]
        """
        pass

    @abstractmethod
    def get_account_transfers(self, filter: LedgerAccountFilter) -> List[LedgerTransfer]:
        """
        Fetch transfers involving a specific account using an account filter.
        """
        pass

    @abstractmethod
    def get_account_balances(self, filter: LedgerAccountFilter) -> List[LedgerAccountBalance]:
        """
        Fetch historical balances for an account using an account filter.
        """
        pass

    @abstractmethod
    def query_accounts(self, query: LedgerQuery) -> List[LedgerAccount]:
        """
        Query accounts by various fields.
        """
        pass

    @abstractmethod
    def query_transfers(self, query: LedgerQuery) -> List[LedgerTransfer]:
        """
        Query transfers by various fields.
        """
        pass

    @abstractmethod
    def query_transactions(self, query: LedgerQuery, journal: bool = True, transfers: bool = True) -> List[LedgerTransaction]:
        """
        Query transactions by various fields.
        """
        pass

    @abstractmethod
    def query_journal(self, query: LedgerQuery) -> List[LedgerJournalEntry]:
        """
        Query journal entries by various fields.
        """
        pass

