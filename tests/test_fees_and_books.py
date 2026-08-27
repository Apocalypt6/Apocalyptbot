from apocalyptbot.books import completeness_buy, merge_sell, walk_asks, walk_bids
from apocalyptbot.fees import FEE_RATES, fee_rate_for, taker_fee
from apocalyptbot.models import Book, Level, Market


def _book(token, bids, asks):
    return Book(
        token_id=token,
        bids=[Level(p, s) for p, s in bids],
        asks=[Level(p, s) for p, s in asks],
    )


def test_taker_fee_tables():
    assert taker_fee(100, 0.50, 0.07) == 1.75
    assert taker_fee(100, 0.50, 0.05) == 1.25
    assert taker_fee(100, 0.50, 0.04) == 1.00
    assert taker_fee(0, 0.5, 0.05) == 0
    assert taker_fee(10, 0.5, 0) == 0


def test_fee_rate_for_maps_fee_type():
    m = Market(id="1", condition_id="0x", question="q", slug="s", fees_enabled=True, fee_type="crypto_fees_v2")
    assert fee_rate_for(m) == FEE_RATES["crypto_fees_v2"]
    assert fee_rate_for(m, override=0.01) == 0.01
    m.fees_enabled = False
    assert fee_rate_for(m) == 0.0
    assert fee_rate_for(None) == 0.0


def test_book_ignores_clob_sort_order():
    book = Book.from_clob(
        {
            "asset_id": "YES",
            "bids": [{"price": "0.001", "size": "10"}, {"price": "0.003", "size": "5"}],
            "asks": [{"price": "0.999", "size": "9"}, {"price": "0.004", "size": "8"}],
            "tick_size": "0.001",
            "min_order_size": "5",
        }
    )
    assert book.best_bid == 0.003
    assert book.best_ask == 0.004
    assert abs(book.mid - 0.0035) < 1e-9
    assert abs(book.spread - 0.001) < 1e-9


def test_walk_asks_and_bids():
    book = _book("t", bids=[(0.40, 10), (0.41, 10)], asks=[(0.42, 5), (0.44, 5)])
    avg, filled = walk_asks(book, 8)
    assert filled == 8
    assert abs(avg - (0.42 * 5 + 0.44 * 3) / 8) < 1e-9
    avg, filled = walk_bids(book, 12)
    assert filled == 12
    assert abs(avg - (0.41 * 10 + 0.40 * 2) / 12) < 1e-9


def test_completeness_buy_top_of_book():
    yes = _book("yes", bids=[(0.39, 10)], asks=[(0.40, 100)])
    no = _book("no", bids=[(0.54, 10)], asks=[(0.55, 80)])
    raw = completeness_buy(yes, no, fee_rate=0.0, min_edge=0.0)
    assert raw is not None
    assert raw["size"] == 80
    assert abs(raw["edge"] - 0.05) < 1e-9
    assert raw["legs"][0][0] == "BUY"
    assert completeness_buy(yes, no, fee_rate=0.0, min_edge=0.06) is None


def test_merge_sell():
    yes = _book("yes", bids=[(0.52, 40)], asks=[(0.53, 10)])
    no = _book("no", bids=[(0.51, 25)], asks=[(0.52, 10)])
    raw = merge_sell(yes, no, fee_rate=0.0, min_edge=0.0)
    assert raw is not None
    assert raw["size"] == 25
    assert abs(raw["edge"] - 0.03) < 1e-9
    assert raw["legs"][0][0] == "SELL"
