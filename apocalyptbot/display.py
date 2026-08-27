"""TTY tables. No extra dependencies."""

from __future__ import annotations

import sys
from typing import Iterable, List, Optional, Sequence


def _tty() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def paint(text: str, color: str) -> str:
    if not _tty():
        return text
    codes = {
        "dim": "\033[2m",
        "bold": "\033[1m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "cyan": "\033[36m",
        "reset": "\033[0m",
    }
    return f"{codes.get(color, '')}{text}{codes['reset']}"


def money(value: Optional[float], digits: int = 0) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    if abs(value) >= 10_000:
        return f"${value/1_000:.1f}k"
    if abs(value) >= 1000:
        return f"${value:,.0f}"
    return f"${value:,.{digits}f}" if digits else f"${value:,.0f}"


def px(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value >= 0.1:
        return f"{value:.3f}"
    return f"{value:.4f}"


def edge_cents(value: Optional[float], kind: str = "") -> str:
    if kind == "whale":
        return "tape"
    if value is None:
        return "—"
    return f"{value * 100:.2f}¢"


def table(headers: Sequence[str], rows: Sequence[Sequence[str]], aligns: Optional[Sequence[str]] = None) -> str:
    cols = len(headers)
    widths = [len(h) for h in headers]
    str_rows: List[List[str]] = []
    for row in rows:
        cells = [str(row[i]) if i < len(row) else "" for i in range(cols)]
        str_rows.append(cells)
        for i, cell in enumerate(cells):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: Sequence[str], header: bool = False) -> str:
        out = []
        for i, cell in enumerate(cells):
            width = widths[i]
            align = (aligns[i] if aligns and i < len(aligns) else ("left" if i == 0 else "right"))
            pad = cell.ljust(width) if align == "left" else cell.rjust(width)
            out.append(paint(pad, "bold") if header else pad)
        return "  ".join(out)

    lines = [fmt(headers, header=True), paint("  ".join("-" * w for w in widths), "dim")]
    lines.extend(fmt(r) for r in str_rows)
    return "\n".join(lines)


def truncate(text: str, n: int = 52) -> str:
    text = (text or "").replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def print_lines(lines: Iterable[str]) -> None:
    for line in lines:
        print(line)
