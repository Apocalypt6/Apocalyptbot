import pytest

from apocalyptbot.broker import PaperBroker
from apocalyptbot.portfolio import Portfolio


def make_broker(cash=10_000.0, fee=0.005, slippage=0.0):
    pf = Portfolio(cash=cash)
    return PaperBroker(pf, fee_rate=fee, slippage=slippage)


def test_buy_deducts_cash_and_adds_position():
    broker = make_broker(cash=1000.0, fee=0.0, slippage=0.0)
    fill = broker.buy("BTC-USD", price=100.0, cash_to_spend=1000.0, timestamp=1)
    assert fill is not None
    assert broker.portfolio.cash == pytest.approx(0.0)
    assert broker.portfolio.quantity("BTC-USD") == pytest.approx(10.0)


def test_buy_charges_fee():
    broker = make_broker(cash=1000.0, fee=0.01, slippage=0.0)
    fill = broker.buy("BTC-USD", price=100.0, cash_to_spend=1000.0, timestamp=1)
    assert fill.fee == pytest.approx(10.0)
    # 990 buys at 100 -> 9.9 units
    assert broker.portfolio.quantity("BTC-USD") == pytest.approx(9.9)


def test_slippage_worsens_prices():
    broker = make_broker(cash=1000.0, fee=0.0, slippage=0.01)
    fill = broker.buy("BTC-USD", price=100.0, cash_to_spend=1000.0, timestamp=1)
    assert fill.price == pytest.approx(101.0)  # paid more when buying


def test_cannot_spend_more_than_cash():
    broker = make_broker(cash=100.0, fee=0.0)
    fill = broker.buy("BTC-USD", price=50.0, cash_to_spend=1_000_000.0, timestamp=1)
    assert broker.portfolio.cash == pytest.approx(0.0)
    assert fill.quantity == pytest.approx(2.0)


def test_dust_order_rejected():
    broker = make_broker(cash=1000.0)
    assert broker.buy("BTC-USD", price=100.0, cash_to_spend=0.5, timestamp=1) is None


def test_sell_realizes_profit():
    broker = make_broker(cash=1000.0, fee=0.0, slippage=0.0)
    broker.buy("BTC-USD", price=100.0, cash_to_spend=1000.0, timestamp=1)  # 10 units @ 100
    fill = broker.sell("BTC-USD", price=150.0, quantity=10.0, timestamp=2)
    assert fill is not None
    assert fill.realized_pnl == pytest.approx(500.0)
    assert broker.portfolio.quantity("BTC-USD") == pytest.approx(0.0)
    assert broker.portfolio.cash == pytest.approx(1500.0)


def test_sell_more_than_held_is_clamped():
    broker = make_broker(cash=1000.0, fee=0.0)
    broker.buy("BTC-USD", price=100.0, cash_to_spend=500.0, timestamp=1)  # 5 units
    fill = broker.sell("BTC-USD", price=100.0, quantity=999.0, timestamp=2)
    assert fill.quantity == pytest.approx(5.0)
    assert broker.portfolio.quantity("BTC-USD") == pytest.approx(0.0)


def test_sell_with_no_position_returns_none():
    broker = make_broker()
    assert broker.sell("BTC-USD", price=100.0, quantity=1.0, timestamp=1) is None


def test_invalid_fee_and_slippage():
    pf = Portfolio(cash=1.0)
    with pytest.raises(ValueError):
        PaperBroker(pf, fee_rate=1.5)
    with pytest.raises(ValueError):
        PaperBroker(pf, slippage=-0.1)
