"""CLI smoke: parser surface and health. No network commands are executed."""

import argparse
import time

import pytest

from apocalyptbot.cli import build_parser, main

REQUIRED = ("scan", "hunt", "tape", "whale", "market", "paper", "live", "health")


def _subcommands(parser: argparse.ArgumentParser) -> set:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_parser_help_exits_zero():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_required_subcommands_exist():
    names = _subcommands(build_parser())
    missing = [name for name in REQUIRED if name not in names]
    assert missing == [], f"missing subcommands: {missing}"


def test_parse_each_subcommand_offline():
    parser = build_parser()
    assert parser.parse_args(["scan"]).command == "scan"
    assert parser.parse_args(["hunt"]).command == "hunt"
    assert parser.parse_args(["tape"]).command == "tape"
    assert parser.parse_args(["whale", "0xabc"]).command == "whale"
    assert parser.parse_args(["market", "some-slug"]).command == "market"
    assert parser.parse_args(["paper", "--once"]).command == "paper"
    assert parser.parse_args(["live"]).command == "live"
    assert parser.parse_args(["health"]).command == "health"


def test_health_missing_heartbeat_returns_1(tmp_path):
    rc = main(["health", "--heartbeat", str(tmp_path / "does-not-exist")])
    assert rc == 1


def test_health_fresh_and_stale(tmp_path):
    hb = tmp_path / "heartbeat"
    hb.write_text(str(int(time.time())))
    assert main(["health", "--heartbeat", str(hb), "--max-age", "60"]) == 0
    hb.write_text(str(int(time.time()) - 10_000))
    assert main(["health", "--heartbeat", str(hb), "--max-age", "60"]) == 1
