"""
Takes the top-N raw XGBoost scores + their feature values and asks a LOCAL
LLM (e.g. via Ollama) to write a one-line human-readable reason for each,
producing the final scoresheet that gets handed to Claude.

This is the "heavy interpretation" layer — it does NOT change the numeric
score (XGBoost's probability is the score of record), it just explains it.
Keeping the numeric score machine-generated avoids the LLM silently
drifting the ranking.

Output schema (data/scoresheet.json):
[
  {"ticker": "AAPL", "score": 82.4, "reason": "Price above both moving averages with rising MACD histogram and strong volume confirmation."},
  ...
]
"""
import json
import logging

import requests
import yaml

from universe import load_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("llm_report")

PROMPT_TEMPLATE = """You are a technical analysis assistant. For each stock below, you are given
its engineered technical features and an XGBoost model's uptrend probability score (0-100,
already computed — do NOT change it). Write ONE concise sentence (max 25 words) explaining
WHY the indicators support (or don't strongly support) that score, in plain English.

Respond ONLY with a JSON array, no other text, in this exact form:
[{{"ticker": "XXXX", "reason": "..."}}, ...]

Stocks:
{stock_block}
"""


def format_stock_block(batch: list[dict]) -> str:
    lines = []
    for item in batch:
        lines.append(f"- {item['ticker']}: xgb_score={item['xgb_score']}, features={item['features']}")
    return "\n".join(lines)


def call_ollama(prompt: str, cfg: dict) -> str:
    resp = requests.post(
        cfg["llm"]["endpoint"],
        json={
            "model": cfg["llm"]["model"],
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
        timeout=cfg["llm"]["timeout_seconds"],
    )
    resp.raise_for_status()
    return resp.json()["response"]


def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    cfg = load_config()

    with open("data/raw_scores.json", "r") as f:
        raw_scores = json.load(f)

    top_n = cfg["scoresheet"]["top_n"]
    top_candidates = raw_scores[:top_n]

    scoresheet = []
    batch_size = cfg["llm"]["max_tickers_per_batch"]
    for batch in chunked(top_candidates, batch_size):
        prompt = PROMPT_TEMPLATE.format(stock_block=format_stock_block(batch))
        try:
            raw_response = call_ollama(prompt, cfg)
            reasons = json.loads(raw_response)
            reason_map = {r["ticker"]: r["reason"] for r in reasons}
        except Exception as e:
            log.warning(f"LLM call/parse failed for batch ({e}); falling back to generic reason.")
            reason_map = {}

        for item in batch:
            scoresheet.append({
                "ticker": item["ticker"],
                "score": item["xgb_score"],
                "reason": reason_map.get(item["ticker"], "LLM reasoning unavailable — score is XGBoost output only."),
            })

    out_path = cfg["scoresheet"]["output_file"]
    with open(out_path, "w") as f:
        json.dump(scoresheet, f, indent=2)
    log.info(f"Wrote scoresheet with {len(scoresheet)} entries to {out_path}")
    log.info("Upload this file to Claude to review candidates and place approved trades.")


if __name__ == "__main__":
    main()
