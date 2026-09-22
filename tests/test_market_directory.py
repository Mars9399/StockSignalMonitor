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
                "currency": "USD",
            }],
        }
        result = MarketDirectoryClient(page_size=100).fetch_page(2)
        self.assertEqual(result.page, 2)
        self.assertEqual(result.total, 321)
        self.assertEqual(result.entries[0].symbol, "AAPL")
        self.assertEqual(result.entries[0].price, 250.5)
        self.assertEqual(result.entries[0].currency, "USD")
        self.assertEqual(result.market, "us")
        self.assertEqual(screen.call_args.kwargs["offset"], 200)

    @patch("market_directory.yf.screen")
    def test_hong_kong_page_uses_hk_region_and_currency(self, screen):
        screen.return_value = {
            "total": 9182,
            "quotes": [{
                "symbol": "0700.HK",
                "shortName": "Tencent Holdings Limited",
                "fullExchangeName": "HKSE",
                "regularMarketPrice": 650.0,
                "regularMarketChangePercent": 2.5,
            }],
        }
        client = MarketDirectoryClient(page_size=100, market="hk")
        result = client.fetch_page(0)
        self.assertEqual(result.market, "hk")
        self.assertEqual(result.entries[0].symbol, "0700.HK")
        self.assertEqual(result.entries[0].currency, "HKD")
        self.assertIn("'hk'", str(client.query))

    @patch("market_directory.yf.Search")
    def test_search_keeps_equities_and_etfs(self, search):
        search.return_value.quotes = [
            {"symbol": "NVDA", "quoteType": "EQUITY", "shortname": "NVIDIA"},
            {"symbol": "NVDA240", "quoteType": "OPTION", "shortname": "Option"},
            {"symbol": "0700.HK", "exchange": "HKG", "quoteType": "EQUITY", "shortname": "Tencent"},
        ]
        result = MarketDirectoryClient(page_size=50).search("nvidia")
        self.assertEqual([entry.symbol for entry in result.entries], ["NVDA"])

    @patch("market_directory.yf.Search")
    def test_hong_kong_search_excludes_us_matches(self, search):
        search.return_value.quotes = [
            {"symbol": "0700.HK", "exchange": "HKG", "quoteType": "EQUITY", "shortname": "Tencent"},
            {"symbol": "TCEHY", "exchange": "PNK", "quoteType": "EQUITY", "shortname": "Tencent ADR"},
        ]
        result = MarketDirectoryClient(page_size=50, market="hk").search("Tencent")
        self.assertEqual([entry.symbol for entry in result.entries], ["0700.HK"])


if __name__ == "__main__":
    unittest.main()
