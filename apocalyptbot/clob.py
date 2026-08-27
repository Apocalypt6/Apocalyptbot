"""CLOB public market data. No auth for reads."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from .http import Http
from .models import Book, Market

CLOB = "https://clob.polymarket.com"
_BOOK_CHUNK = 80


class Clob:
    def __init__(self, http: Optional[Http] = None):
        self.http = http or Http()

    def book(self, token_id: str) -> Book:
        payload = self.http.get(f"{CLOB}/book", params={"token_id": token_id})
        if not isinstance(payload, dict):
            return Book(token_id=token_id)
        return Book.from_clob(payload)

    def books(self, token_ids: Sequence[str]) -> Dict[str, Book]:
        out: Dict[str, Book] = {}
        ids = [tid for tid in token_ids if tid]
        for start in range(0, len(ids), _BOOK_CHUNK):
            chunk = ids[start : start + _BOOK_CHUNK]
            payload = [{"token_id": tid} for tid in chunk]
            data = self.http.post(f"{CLOB}/books", payload)
            rows = data if isinstance(data, list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                book = Book.from_clob(row)
                if book.token_id:
                    out[book.token_id] = book
        return out

    def attach_books(self, markets: Iterable[Market]) -> List[Market]:
        markets = list(markets)
        token_ids = [tid for market in markets for tid in market.token_ids()]
        books = self.books(token_ids)
        for market in markets:
            for outcome in market.outcomes:
                outcome.book = books.get(outcome.token_id)
        return markets
