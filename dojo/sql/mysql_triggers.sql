DELIMITER //
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

----------------------------------------------

DELIMITER //
CREATE TRIGGER tx_balance_update
AFTER UPDATE ON ledger_accounts
FOR EACH ROW
BEGIN
  INSERT INTO ledger_account_log (account_id, last_tx, last_balance, this_tx, balance)
  VALUES (OLD.id, OLD.last_tx, OLD.balance, NEW.last_tx, NEW.balance);
END

----------------------------------------------

