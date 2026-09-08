"""
Checks all OPEN positions in the database against current prices and flags
any that have hit their stop-loss. Does NOT close positions or place
sell orders itself — writes data/exits_needed.json for Claude to review
and execute (with your approval) on the Robinhood side, same as entries.
"""
import json
import logging

import yfinance as yf

from position_tracking import get_open_positions
from stop_loss import check_stop_triggered

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("check_exits")


def main():
    open_positions = get_open_positions()
    if not open_positions:
        log.info("No open positions to check.")
        with open("data/exits_needed.json", "w") as f:
            json.dump([], f)
        return

    tickers = [p["ticker"] for p in open_positions]
    quotes = yf.download(tickers=tickers, period="1d", interval="1d", progress=False, group_by="ticker")

    flagged = []
    for pos in open_positions:
        ticker = pos["ticker"]
        try:
            current_price = quotes[ticker]["Close"].iloc[-1] if len(tickers) > 1 else quotes["Close"].iloc[-1]
        except (KeyError, IndexError):
            log.warning(f"Could not get current price for {ticker}, skipping.")
            continue

        if check_stop_triggered(current_price, pos["stop_loss_price"]):
            flagged.append({
                "position_id": pos["id"],
                "ticker": ticker,
                "entry_price": pos["entry_price"],
                "current_price": float(current_price),
                "stop_loss_price": pos["stop_loss_price"],
                "unrealized_pnl_pct": round((float(current_price) / pos["entry_price"] - 1) * 100, 2),
            })

    with open("data/exits_needed.json", "w") as f:
        json.dump(flagged, f, indent=2)

    log.info(f"Checked {len(open_positions)} open positions. {len(flagged)} hit stop-loss.")


if __name__ == "__main__":
    main()
