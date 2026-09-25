from .base import MarketDataProvider, NewsItem
from .csv_provider import CSVProvider
from .synthetic import SyntheticProvider
from .yahoo import YahooProvider

PROVIDERS = {"synthetic": SyntheticProvider, "yahoo": YahooProvider, "csv": CSVProvider}


def get_provider(config: dict) -> MarketDataProvider:
    name = config.get("data_provider", "synthetic")
    try:
        return PROVIDERS[name](config)
    except KeyError:
        raise ValueError(f"unknown data_provider {name!r}; choose from {sorted(PROVIDERS)}")


__all__ = ["MarketDataProvider", "NewsItem", "SyntheticProvider", "YahooProvider",
           "CSVProvider", "get_provider", "PROVIDERS"]
