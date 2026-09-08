"""
Builds the ticker universe to scan.

Default: S&P 500 constituents, scraped from Wikipedia (free, no API key).
Falls back to a small hardcoded list if the scrape fails, so the pipeline
never hard-stops.
"""
import logging
import pandas as pd
import yaml

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("universe")

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

FALLBACK_TICKERS = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "HD", "PG", "MA", "XOM", "COST", "JNJ", "AVGO",
]


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def get_sp500_tickers() -> list[str]:
    try:
        tables = pd.read_html(WIKI_SP500_URL)
        df = tables[0]
        tickers = df["Symbol"].tolist()
        # yfinance wants dots as dashes for tickers like BRK.B -> BRK-B
        tickers = [t.replace(".", "-") for t in tickers]
        log.info(f"Pulled {len(tickers)} S&P 500 tickers from Wikipedia.")
        return tickers
    except Exception as e:
        log.warning(f"Wikipedia scrape failed ({e}); using fallback list of {len(FALLBACK_TICKERS)} tickers.")
        return FALLBACK_TICKERS


def get_custom_tickers(path: str) -> list[str]:
    with open(path, "r") as f:
        return [line.strip().upper() for line in f if line.strip()]


def get_universe(config: dict) -> list[str]:
    source = config["universe"]["source"]
    if source == "sp500":
        return get_sp500_tickers()
    elif source == "custom":
        return get_custom_tickers(config["universe"]["custom_tickers_file"])
    else:
        raise ValueError(f"Unknown universe source: {source}")


if __name__ == "__main__":
    cfg = load_config()
    tickers = get_universe(cfg)
    print(f"Universe size: {len(tickers)}")
    print(tickers[:20], "...")
