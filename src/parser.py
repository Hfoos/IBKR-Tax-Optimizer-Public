import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class Transaction:
    account: str             # IBKR account ID (e.g. U1234567)
    symbol: str
    currency: str           # USD, GBP, or EUR
    date: date
    quantity: float         # positive = buy/transfer-in, negative = sell
    price: float            # per share in original currency
    commission: float       # always positive (absolute cost)
    is_transfer: bool = False   # True when the lot came via an account transfer


def _extract_account(filepath: Path) -> str:
    """Extract account ID from IBKR filename: U1234567_2022_activity.csv → U1234567."""
    return filepath.stem.split("_")[0]


def parse_all_csvs(data_folder: str) -> list[Transaction]:
    transactions = []
    folder = Path(data_folder)
    for filepath in sorted(folder.glob("*.csv")):
        transactions.extend(_parse_file(filepath))
    return sorted(transactions, key=lambda t: t.date)


def get_csv_filenames(data_folder: str) -> list[str]:
    return sorted(p.name for p in Path(data_folder).glob("*.csv"))


def parse_open_positions(data_folder: str) -> dict[str, dict[str, float]]:
    """
    Parse Open Positions from the most recent CSV file per account.

    Returns {account: {symbol: quantity}} reflecting what IBKR actually reports as held.
    This is the authoritative source — it correctly handles corporate actions,
    account transfers, and symbol renames that the Trades-only parser cannot see.
    """
    folder = Path(data_folder)
    account_files: dict[str, list[Path]] = defaultdict(list)
    for f in folder.glob("*.csv"):
        account_files[_extract_account(f)].append(f)

    result = {}
    for account, files in account_files.items():
        for filepath in reversed(sorted(files)):
            positions = _parse_open_positions_file(filepath)
            if positions:
                result[account] = positions
                break
    return result


def _parse_open_positions_file(filepath: Path) -> dict[str, float]:
    positions = {}
    with open(filepath, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if (
                len(row) >= 7
                and row[0] == "Open Positions"
                and row[1] == "Data"
                and row[2] == "Summary"
                and row[3] == "Stocks"
            ):
                try:
                    symbol = row[5].strip()
                    quantity = float(row[6].replace(",", ""))
                    if quantity > 0:
                        positions[symbol] = quantity
                except (ValueError, IndexError):
                    continue
    return positions


def _parse_file(filepath: Path) -> list[Transaction]:
    account = _extract_account(filepath)
    transactions = []
    with open(filepath, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            txn = _try_parse_trade(row, account) or _try_parse_transfer_in(row, account)
            if txn:
                transactions.append(txn)
    return transactions


def _try_parse_trade(row: list[str], account: str):
    if not (
        len(row) >= 12
        and row[0] == "Trades"
        and row[1] == "Data"
        and row[2] == "Order"
        and row[3] == "Stocks"
    ):
        return None
    try:
        currency = row[4].strip()
        symbol = row[5].strip()
        date_str = row[6].split(",")[0].strip()
        trade_date = date.fromisoformat(date_str)
        quantity = float(row[7].replace(",", ""))
        price = float(row[8].replace(",", ""))
        commission = abs(float(row[11].replace(",", "")))
        return Transaction(account=account, symbol=symbol, currency=currency,
                           date=trade_date, quantity=quantity, price=price,
                           commission=commission)
    except (ValueError, IndexError):
        return None


def _try_parse_transfer_in(row: list[str], account: str):
    """
    Parse inbound position transfers.

    Format: Transfers,Data,Stocks,{currency},{symbol},{date},{type},In,--,{source},{qty},--,{cost},...
    The cost field is in the stock's native currency and represents IBKR's recorded
    value at transfer time — used as cost basis in the absence of original records.
    """
    if not (
        len(row) >= 13
        and row[0] == "Transfers"
        and row[1] == "Data"
        and row[2] == "Stocks"
        and row[7] == "In"
    ):
        return None
    try:
        currency = row[3].strip()
        symbol = row[4].strip()
        transfer_date = date.fromisoformat(row[5].strip())
        quantity = float(row[10].replace(",", ""))
        if quantity <= 0:
            return None
        total_cost = abs(float(row[12].replace(",", "").replace('"', "")))
        price_per_share = total_cost / quantity if quantity else 0.0
        return Transaction(account=account, symbol=symbol, currency=currency,
                           date=transfer_date, quantity=quantity,
                           price=price_per_share, commission=0.0, is_transfer=True)
    except (ValueError, IndexError, ZeroDivisionError):
        return None
