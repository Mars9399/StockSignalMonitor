import unittest
from unittest.mock import patch

from market_directory import MarketDirectoryClient


class MarketDirectoryTests(unittest.TestCase):
    @patch("market_directory.yf.screen")
    def test_fetch_page_normalizes_quotes(self, screen):
        screen.return_value = {
            "total": 321,
            "quotes": [{
                "symbol": "aapl",
                "shortName": "Apple Inc.",
                "fullExchangeName": "NasdaqGS",
                "regularMarketPrice": 250.5,
                "regularMarketChangePercent": 1.25,
                "regularMarketVolume": 123456,
                "marketCap": 3_000_000_000_000,
            }],
        }
        result = MarketDirectoryClient(page_size=100).fetch_page(2)
        self.assertEqual(result.page, 2)
        self.assertEqual(result.total, 321)
        self.assertEqual(result.entries[0].symbol, "AAPL")
        self.assertEqual(result.entries[0].price, 250.5)
        self.assertEqual(screen.call_args.kwargs["offset"], 200)

    @patch("market_directory.yf.Search")
    def test_search_keeps_equities_and_etfs(self, search):
        search.return_value.quotes = [
            {"symbol": "NVDA", "quoteType": "EQUITY", "shortname": "NVIDIA"},
            {"symbol": "NVDA240", "quoteType": "OPTION", "shortname": "Option"},
        ]
        result = MarketDirectoryClient(page_size=50).search("nvidia")
        self.assertEqual([entry.symbol for entry in result.entries], ["NVDA"])


if __name__ == "__main__":
    unittest.main()
