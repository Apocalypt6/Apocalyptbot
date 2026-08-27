"""Parsing helpers and typed Gamma / CLOB / tape records."""

import pytest

from apocalyptbot.models import (
    Book,
    Level,
    Market,
    Print,
    as_float,
    index_by_condition,
    maybe_json,
)
from tests.conftest import make_binary_market, make_opportunity, make_unsorted_clob_payload


def test_maybe_json_parses_encoded_arrays_and_objects():
    assert maybe_json('["Yes", "No"]') == ["Yes", "No"]
    assert maybe_json('{"a": 1}') == {"a": 1}


def test_maybe_json_passthrough_list_dict_none():
    assert maybe_json(["Yes", "No"]) == ["Yes", "No"]
    assert maybe_json({"a": 1}) == {"a": 1}
    assert maybe_json(None) is None


def test_maybe_json_empty_and_invalid():
    assert maybe_json("") is None
    assert maybe_json("   ") is None
    assert maybe_json("not-json") == "not-json"
    assert maybe_json("[bad") == "[bad"]


def test_as_float_casts_and_defaults():
    assert as_float("1.5") == 1.5
    assert as_float(2) == 2.0
    assert as_float(None) is None
    assert as_float(None, 0.0) == 0.0
    assert as_float("", 3.0) == 3.0
    assert as_float("nope", 3.0) == 3.0
    assert as_float("1e-2") == pytest.approx(0.01)


def test_book_from_clob_ignores_sort_order():
    # bids 0.001, 0.002, 0.003 and asks 0.999, 0.998, 0.004
    book = Book.from_clob(make_unsorted_clob_payload("YES"))
    assert book.token_id == "YES"
    assert book.best_bid == pytest.approx(0.003)
    assert book.best_ask == pytest.approx(0.004)
    assert book.mid == pytest.approx(0.0035)
    assert book.spread == pytest.approx(0.001)


def test_book_mid_and_spread_edge_cases():
    only_bid = Book(token_id="t", bids=[Level(0.4, 1)])
    assert only_bid.best_ask is None
    assert only_bid.mid == pytest.approx(0.4)
    assert only_bid.spread is None

    only_ask = Book(token_id="t", asks=[Level(0.6, 1)])
    assert only_ask.mid == pytest.approx(0.6)
    assert only_ask.spread is None

    empty = Book(token_id="t", last_trade_price=0.55)
    assert empty.mid == pytest.approx(0.55)
    assert empty.spread is None


def test_book_from_clob_skips_bad_levels_and_reads_token_id():
    book = Book.from_clob(
        {
            "token_id": "alt",
            "bids": [
                {"price": "0.2", "size": "0"},
                {"price": None, "size": "3"},
                {"price": "0.3", "size": "4"},
            ],
            "asks": [{"price": "0.9", "size": "2"}],
        }
    )
    assert book.token_id == "alt"
    assert book.best_bid == pytest.approx(0.3)
    assert [lvl.size for lvl in book.bids] == [4.0]


def test_market_from_gamma_json_strings():
    payload = {
        "id": "m1",
        "conditionId": "0xabc",
        "question": "Will it rain?",
        "slug": "will-it-rain",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["tok-yes", "tok-no"]',
        "outcomePrices": '["0.4", "0.6"]',
        "volume24hr": "1000",
        "feesEnabled": True,
        "feeType": "crypto_fees",
    }
    market = Market.from_gamma(payload)
    assert market.is_binary
    assert market.yes is not None and market.yes.name == "Yes"
    assert market.yes.token_id == "tok-yes"
    assert market.yes.price == pytest.approx(0.4)
    assert market.no is not None and market.no.name == "No"
    assert market.no.token_id == "tok-no"
    assert market.volume_24h == pytest.approx(1000.0)
    assert market.fees_enabled is True
    assert market.fee_type == "crypto_fees"


def test_market_from_gamma_native_lists_and_event():
    payload = {
        "id": "m2",
        "condition_id": "0xdef",
        "slug": "up-or-down",
        "outcomes": ["Up", "Down"],
        "clobTokenIds": ["tok-up", "tok-down"],
        "outcomePrices": [0.55, 0.45],
    }
    event = {"title": "Macro", "slug": "macro", "endDate": "2026-12-01T00:00:00Z"}
    market = Market.from_gamma(payload, event=event)
    assert market.question == "Macro"
    assert market.event_title == "Macro"
    assert market.event_slug == "macro"
    assert market.end_date == "2026-12-01T00:00:00Z"
    # names are not Yes/No → first/second
    assert market.yes is not None and market.yes.name == "Up"
    assert market.no is not None and market.no.name == "Down"
    assert market.is_binary


def test_market_yes_no_resolved_by_name_not_order():
    payload = {
        "id": "m3",
        "conditionId": "0x1",
        "slug": "flip",
        "question": "flip",
        "outcomes": '["No", "Yes"]',
        "clobTokenIds": '["tok-no", "tok-yes"]',
        "outcomePrices": '["0.6", "0.4"]',
    }
    market = Market.from_gamma(payload)
    assert market.yes.token_id == "tok-yes"
    assert market.no.token_id == "tok-no"


def test_market_from_gamma_nested_events_array():
    payload = {
        "id": "m4",
        "conditionId": "0x4",
        "slug": "nested",
        "question": "",
        "outcomes": ["Yes"],
        "clobTokenIds": ["only"],
        "events": [{"title": "From nested", "slug": "nested-event"}],
    }
    market = Market.from_gamma(payload)
    assert market.event_title == "From nested"
    assert market.is_binary is False


def test_print_from_api_usd_and_wallet():
    print_ = Print.from_api(
        {
            "proxyWallet": "0xwallet",
            "side": "buy",
            "asset": "tok",
            "conditionId": "0xc",
            "size": "100",
            "price": "0.55",
            "title": "T",
            "slug": "s",
            "outcome": "Yes",
            "timestamp": "123",
            "name": "bob",
            "transactionHash": "0xtx",
        }
    )
    assert print_.usd == pytest.approx(55.0)
    assert print_.wallet == "0xwallet"
    assert print_.side == "BUY"
    assert print_.token_id == "tok"
    assert print_.name == "bob"
    assert print_.tx == "0xtx"
    assert print_.timestamp == 123


def test_print_from_api_wallet_falls_back_to_user():
    print_ = Print.from_api({"user": "0xuser", "size": 10, "price": 0.2, "side": "SELL"})
    assert print_.wallet == "0xuser"
    assert print_.usd == pytest.approx(2.0)
    assert print_.side == "SELL"


def test_opportunity_with_size_scales_legs_and_notional():
    market = make_binary_market()
    opp = make_opportunity(market, size=80, yes_px=0.40, no_px=0.55, edge=0.05)
    assert opp.notional == pytest.approx(76.0)
    scaled = opp.with_size(40)
    assert scaled is not opp
    assert scaled.size == pytest.approx(40)
    assert scaled.notional == pytest.approx(38.0)
    assert scaled.edge == pytest.approx(0.05)
    assert scaled.kind == "completeness"
    assert scaled.legs[0][3] == pytest.approx(40)
    assert scaled.legs[1][3] == pytest.approx(40)
    assert scaled.legs[0][2] == pytest.approx(0.40)


def test_opportunity_with_size_nonpositive_returns_self():
    market = make_binary_market()
    opp = make_opportunity(market)
    assert opp.with_size(0) is opp
    assert opp.with_size(-5) is opp


def test_index_by_condition():
    a = make_binary_market(condition_id="0xaa")
    b = make_binary_market(condition_id="0xbb", slug="other")
    blank = Market(id="z", condition_id="", question="q", slug="z")
    idx = index_by_condition([a, b, blank])
    assert set(idx) == {"0xaa", "0xbb"}
    assert idx["0xaa"] is a
