"""Paged, read-only US market directory backed by Yahoo Finance screening."""

from __future__ import annotations

from dataclasses import dataclass
import math

import yfinance as yf
from yfinance import EquityQuery


@dataclass(frozen=True)
class MarketDirectoryEntry:
    symbol: str
    name: str
    exchange: str
    price: float
    change_pct: float
    volume: int
    market_cap: float


@dataclass(frozen=True)
class MarketDirectoryPage:
    entries: list[MarketDirectoryEntry]
    page: int
    page_size: int
    total: int


class MarketDirectoryClient:
    """Read one Yahoo screen page at a time so large markets stay responsive."""

    def __init__(self, page_size: int = 100):
        self.page_size = max(25, min(250, page_size))
        self.query = EquityQuery(
            "and",
            [
                EquityQuery("eq", ["region", "us"]),
                EquityQuery("gt", ["intradayprice", 0]),
            ],
        )

    def fetch_page(self, page: int = 0) -> MarketDirectoryPage:
        page = max(0, int(page))
        payload = yf.screen(
            self.query,
            offset=page * self.page_size,
            size=self.page_size,
            sortField="ticker",
            sortAsc=True,
        )
        entries: list[MarketDirectoryEntry] = []
        for quote in payload.get("quotes", []):
            symbol = str(quote.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            entries.append(
                MarketDirectoryEntry(
                    symbol=symbol,
                    name=str(quote.get("shortName") or quote.get("longName") or symbol),
                    exchange=str(quote.get("fullExchangeName") or quote.get("exchange") or "—"),
                    price=self._number(quote.get("regularMarketPrice")),
                    change_pct=self._number(quote.get("regularMarketChangePercent")),
                    volume=max(0, int(self._number(quote.get("regularMarketVolume")))),
                    market_cap=max(0, self._number(quote.get("marketCap"))),
                )
            )
        return MarketDirectoryPage(
            entries=entries,
            page=page,
            page_size=self.page_size,
            total=max(0, int(payload.get("total", len(entries)) or len(entries))),
        )

    def search(self, text: str) -> MarketDirectoryPage:
        query = text.strip()
        if not query:
            return self.fetch_page(0)
        quotes = yf.Search(query, max_results=self.page_size, news_count=0).quotes
        payload = {
            "quotes": [
                quote for quote in quotes
                if str(quote.get("quoteType", "")).upper() in {"EQUITY", "ETF"}
            ],
            "total": len(quotes),
        }
        entries: list[MarketDirectoryEntry] = []
        for quote in payload["quotes"]:
            symbol = str(quote.get("symbol", "")).strip().upper()
            if symbol:
                entries.append(
                    MarketDirectoryEntry(
                        symbol=symbol,
                        name=str(quote.get("shortname") or quote.get("longname") or symbol),
                        exchange=str(quote.get("exchDisp") or quote.get("exchange") or "—"),
                        price=self._number(quote.get("regularMarketPrice")),
                        change_pct=self._number(quote.get("regularMarketChangePercent")),
                        volume=max(0, int(self._number(quote.get("regularMarketVolume")))),
                        market_cap=max(0, self._number(quote.get("marketCap"))),
                    )
                )
        return MarketDirectoryPage(entries=entries, page=0, page_size=self.page_size, total=len(entries))

    @staticmethod
    def _number(value) -> float:
        try:
            number = float(value or 0)
            return number if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0
