"""Order-book walks, completeness buys, and merge sells."""

import pytest

from apocalyptbot.books import completeness_buy, merge_sell, walk_asks, walk_bids
from apocalyptbot.fees import taker_fee
from tests.conftest import make_book, make_binary_market


def test_walk_asks_average_price_and_fill():
    book = make_book("t", asks=[(0.42, 5), (0.44, 5)])
    avg, filled = walk_asks(book, 8)
    assert filled == 8
    assert avg == pytest.approx((0.42 * 5 + 0.44 * 3) / 8)


def test_walk_bids_hits_best_bid_first():
    book = make_book("t", bids=[(0.40, 10), (0.41, 10)])
    avg, filled = walk_bids(book, 12)
    assert filled == 12
    assert avg == pytest.approx((0.41 * 10 + 0.40 * 2) / 12)


def test_walk_sorts_unsorted_levels():
    # CLOB rows arrive in arbitrary order; walks must still take the inside first.
    book = make_book("t", asks=[(0.50, 10), (0.40, 10)], bids=[(0.10, 10), (0.30, 10)])
    avg, filled = walk_asks(book, 10)
    assert filled == 10
    assert avg == pytest.approx(0.40)
    avg, filled = walk_bids(book, 10)
    assert filled == 10
    assert avg == pytest.approx(0.30)


def test_walk_zero_or_empty():
    book = make_book("t", asks=[(0.50, 10)], bids=[(0.40, 10)])
    assert walk_asks(book, 0) == (0.0, 0.0)
    assert walk_asks(book, -5) == (0.0, 0.0)
    assert walk_bids(make_book("empty"), 10) == (0.0, 0.0)


def test_walk_partial_when_book_is_thin():
    book = make_book("t", asks=[(0.50, 7)])
    avg, filled = walk_asks(book, 100)
    assert filled == 7
    assert avg == pytest.approx(0.50)


def test_completeness_buy_canonical_example():
    # Yes ask 0.40 (100) and No ask 0.55 (80), fee_rate 0 → size 80, edge 0.05
    yes = make_book("yes", bids=[(0.39, 10)], asks=[(0.40, 100)])
    no = make_book("no", bids=[(0.54, 10)], asks=[(0.55, 80)])
    raw = completeness_buy(yes, no, fee_rate=0.0, min_edge=0.0)
    assert raw is not None
    assert raw["size"] == pytest.approx(80)
    assert raw["edge"] == pytest.approx(0.05)
    assert raw["yes_avg"] == pytest.approx(0.40)
    assert raw["no_avg"] == pytest.approx(0.55)
    assert raw["fees"] == pytest.approx(0.0)
    assert raw["notional"] == pytest.approx(0.40 * 80 + 0.55 * 80)
    assert raw["legs"][0][0] == "BUY"
    assert raw["legs"][1][0] == "BUY"
    assert raw["legs"][0][1] == "yes"
    assert raw["legs"][1][1] == "no"
    assert raw["legs"][0][3] == pytest.approx(80)
    assert raw["legs"][0][4] == "Yes"
    assert raw["legs"][1][4] == "No"


def test_completeness_buy_none_when_no_edge():
    yes = make_book("yes", asks=[(0.50, 100)])
    no = make_book("no", asks=[(0.51, 100)])
    assert completeness_buy(yes, no, fee_rate=0.0, min_edge=0.0) is None
    # same 0.40+0.55 book, but min_edge above the 5¢
    yes = make_book("yes", asks=[(0.40, 100)])
    no = make_book("no", asks=[(0.55, 80)])
    assert completeness_buy(yes, no, fee_rate=0.0, min_edge=0.06) is None


def test_completeness_buy_none_when_a_side_is_empty():
    yes = make_book("yes", asks=[(0.40, 100)])
    assert completeness_buy(yes, make_book("no"), fee_rate=0.0) is None


def test_completeness_buy_respects_max_shares_and_names():
    yes = make_book("yes", asks=[(0.40, 100)])
    no = make_book("no", asks=[(0.55, 80)])
    raw = completeness_buy(
        yes, no, fee_rate=0.0, min_edge=0.0, max_shares=10, yes_name="Up", no_name="Down"
    )
    assert raw is not None
    assert raw["size"] == pytest.approx(10)
    assert raw["legs"][0][4] == "Up"
    assert raw["legs"][1][4] == "Down"


def test_completeness_buy_subtracts_taker_fees_from_edge():
    yes = make_book("yes", asks=[(0.40, 100)])
    no = make_book("no", asks=[(0.55, 80)])
    raw = completeness_buy(yes, no, fee_rate=0.05, min_edge=0.0)
    assert raw is not None
    expected_fees = taker_fee(80, 0.40, 0.05) + taker_fee(80, 0.55, 0.05)
    assert raw["fees"] == pytest.approx(expected_fees)
    assert raw["edge"] == pytest.approx((1.0 - 0.40 - 0.55) - expected_fees / 80)
    assert raw["edge"] < 0.05


def test_merge_sell_when_bids_sum_above_one():
    yes = make_book("yes", bids=[(0.52, 40)], asks=[(0.53, 10)])
    no = make_book("no", bids=[(0.51, 25)], asks=[(0.52, 10)])
    raw = merge_sell(yes, no, fee_rate=0.0, min_edge=0.0)
    assert raw is not None
    assert raw["size"] == pytest.approx(25)
    assert raw["edge"] == pytest.approx(0.03)
    assert raw["yes_avg"] == pytest.approx(0.52)
    assert raw["no_avg"] == pytest.approx(0.51)
    assert raw["legs"][0][0] == "SELL"
    assert raw["legs"][1][0] == "SELL"
    assert raw["notional"] == pytest.approx(0.52 * 25 + 0.51 * 25)


def test_merge_sell_none_when_bids_do_not_clear_a_dollar():
    yes = make_book("yes", bids=[(0.40, 50)])
    no = make_book("no", bids=[(0.50, 50)])
    assert merge_sell(yes, no, fee_rate=0.0, min_edge=0.0) is None


def test_merge_sell_none_when_min_edge_not_met():
    yes = make_book("yes", bids=[(0.52, 40)])
    no = make_book("no", bids=[(0.51, 25)])
    assert merge_sell(yes, no, fee_rate=0.0, min_edge=0.05) is None


def test_helpers_work_on_market_attached_books():
    market = make_binary_market()
    raw = completeness_buy(market.yes.book, market.no.book, fee_rate=0.0)
    assert raw is not None
    assert raw["size"] == pytest.approx(80)
    assert raw["edge"] == pytest.approx(0.05)
