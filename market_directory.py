"""Paged, read-only US/Hong Kong market directory backed by Yahoo screening."""

from __future__ import annotations

from dataclasses import dataclass
import math

import yfinance as yf
from yfinance import EquityQuery


SUPPORTED_MARKETS = {"us", "hk"}
HONG_KONG_EXCHANGES = {"HKG", "HKSE", "HONG KONG"}


@dataclass(frozen=True)
class MarketDirectoryEntry:
    symbol: str
    name: str
    exchange: str
    price: float
    change_pct: float
    volume: int
    market_cap: float
    currency: str


@dataclass(frozen=True)
class MarketDirectoryPage:
    entries: list[MarketDirectoryEntry]
    page: int
    page_size: int
    total: int
    market: str


class MarketDirectoryClient:
    """Read one Yahoo screen page at a time so large markets stay responsive."""

    def __init__(self, page_size: int = 100, market: str = "us"):
        self.page_size = max(25, min(250, page_size))
        normalized_market = market.strip().lower()
        if normalized_market not in SUPPORTED_MARKETS:
            raise ValueError(f"unsupported market: {market}")
        self.market = normalized_market
        self.query = EquityQuery(
            "and",
            [
                EquityQuery("eq", ["region", self.market]),
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
                    currency=str(quote.get("currency") or ("HKD" if self.market == "hk" else "USD")),
                )
            )
        return MarketDirectoryPage(
            entries=entries,
            page=page,
            page_size=self.page_size,
            total=max(0, int(payload.get("total", len(entries)) or len(entries))),
            market=self.market,
        )

    def search(self, text: str) -> MarketDirectoryPage:
        query = text.strip()
        if not query:
            return self.fetch_page(0)
        quotes = yf.Search(query, max_results=self.page_size, news_count=0).quotes
        filtered_quotes = [
            quote for quote in quotes
            if str(quote.get("quoteType", "")).upper() in {"EQUITY", "ETF"}
            and self._matches_market(quote)
        ]
        entries: list[MarketDirectoryEntry] = []
        for quote in filtered_quotes:
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
                        currency=str(quote.get("currency") or ("HKD" if self.market == "hk" else "USD")),
                    )
                )
        return MarketDirectoryPage(
            entries=entries,
            page=0,
            page_size=self.page_size,
            total=len(entries),
            market=self.market,
        )

    def _matches_market(self, quote: dict) -> bool:
        symbol = str(quote.get("symbol", "")).strip().upper()
        exchange = str(
            quote.get("exchange") or quote.get("exchDisp") or quote.get("fullExchangeName") or ""
        ).strip().upper()
        is_hong_kong = symbol.endswith(".HK") or exchange in HONG_KONG_EXCHANGES
        return is_hong_kong if self.market == "hk" else not is_hong_kong

    @staticmethod
    def _number(value) -> float:
        try:
            number = float(value or 0)
            return number if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0
