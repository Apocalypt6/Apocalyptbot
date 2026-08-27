import pytest

from apocalyptbot.cli import build_parser, main
from apocalyptbot.research import ResearchDisabled, estimate_exa_cost, run_research


def test_parser_has_beast_commands():
    parser = build_parser()
    for name in ("scan", "hunt", "tape", "whale", "market", "paper", "live", "health", "research"):
        args = parser.parse_args([name] if name != "whale" and name != "market" and name != "research" else [name, "x"])
        assert args.command == name


def test_help_exits_zero():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_health_missing_file(tmp_path):
    rc = main(["health", "--heartbeat", str(tmp_path / "nope")])
    assert rc == 1


def test_live_refuses_without_flag():
    assert main(["live", "--once"]) == 2


def test_research_refuses():
    assert estimate_exa_cost(1) == 0.007
    with pytest.raises(ResearchDisabled):
        run_research("fed", budget_usd=0)
    assert main(["research", "anything"]) == 2
