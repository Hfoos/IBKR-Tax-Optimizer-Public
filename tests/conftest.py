"""Shared fixtures for the IBKR Tax Optimizer test suite."""
import pytest
from datetime import date
from src.portfolio import Lot
from src.parser import Transaction


@pytest.fixture
def make_lot():
    def _factory(
        account="IB001",
        symbol="AAPL",
        currency="USD",
        purchase_date=date(2022, 1, 1),
        original_qty=100.0,
        remaining_qty=None,
        purchase_price=100.0,
        purchase_commission=0.0,
        purchase_rate=3.5,
        is_transfer=False,
    ) -> Lot:
        return Lot(
            account=account,
            symbol=symbol,
            currency=currency,
            purchase_date=purchase_date,
            original_qty=original_qty,
            remaining_qty=remaining_qty if remaining_qty is not None else original_qty,
            purchase_price=purchase_price,
            purchase_commission=purchase_commission,
            purchase_rate=purchase_rate,
            is_transfer=is_transfer,
        )
    return _factory


@pytest.fixture
def make_txn():
    def _factory(
        account="IB001",
        symbol="AAPL",
        currency="USD",
        txn_date=date(2022, 1, 1),
        quantity=100.0,
        price=100.0,
        commission=0.0,
        is_transfer=False,
    ) -> Transaction:
        return Transaction(
            account=account,
            symbol=symbol,
            currency=currency,
            date=txn_date,
            quantity=quantity,
            price=price,
            commission=commission,
            is_transfer=is_transfer,
        )
    return _factory
