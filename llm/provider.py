"""
Model providers behind one interface. Phase ADO.

WHY AN ABSTRACTION FOR A SINGLE PROVIDER
-----------------------------------------
Because the point of ADO is that the implementation model is *replaceable*. If
DeepSeek calls are scattered through the orchestrator, swapping models means
rewriting the orchestration; if they sit behind this interface, it means adding
one class. The cost difference between providers is the reason ADO exists, so
the ability to move is the feature.

CREDENTIALS NEVER TOUCH THE REPO
---------------------------------
Keys are read from a 0600 file in the home directory, matching what
`delistings.py` and `notify.py` already do for Alpha Vantage and Telegram. They
are never logged, never committed, never included in a task payload, and never
echoed in an error message — `_redact` scrubs anything key-shaped out of API
error bodies before they are raised.

EVERY CALL IS METERED
---------------------
Token counts and estimated cost are recorded per call against the task that
caused them. Without that, "offload work to the cheaper model" is a belief
rather than a measurement, and the first question anyone sensible asks is what
it actually saved.

The model is pinned explicitly. `deepseek-chat` currently resolves to
`deepseek-flash`, and a task record that does not say which model produced an
implementation cannot be reviewed properly six weeks later.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("llm")


class LLMError(RuntimeError):
    """Provider failure. Never carries a credential — see _redact."""


def _redact(text: str) -> str:
    """Strip anything key-shaped before an error body is logged or raised."""
    return re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***REDACTED***", text or "")


@dataclass
class Response:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    provider: str = ""
    raw_finish_reason: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def cost_usd(self, rates: dict) -> float:
        """Estimated, from configured per-million rates. Rates change; this is a meter, not an invoice."""
        return (self.prompt_tokens / 1e6 * float(rates.get("input_per_mtok", 0))
                + self.completion_tokens / 1e6 * float(rates.get("output_per_mtok", 0)))


class LLMProvider:
    """Every provider implements exactly this."""

    name = "base"

    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float = 0.0) -> Response:
        raise NotImplementedError


class DeepSeekProvider(LLMProvider):
    name = "deepseek"
    KEY_FILE = Path.home() / ".deepseek_key"
    URL = "https://api.deepseek.com/chat/completions"

    def __init__(self, model: str = "deepseek-chat", key_file: Path | None = None,
                 attempts: int = 3, timeout: int = 300):
        self.model = model
        self.key_file = key_file or self.KEY_FILE
        self.attempts = attempts
        self.timeout = timeout

    def _key(self) -> str:
        if not self.key_file.exists():
            raise LLMError(
                f"{self.key_file} not found. Create it with mode 0600; the key "
                f"must never be placed in the repository or in a task file.")
        k = self.key_file.read_text().strip()
        if not k or k == "sk-YOUR_KEY":
            raise LLMError(f"{self.key_file} holds a placeholder, not a key.")
        return k

    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float = 0.0) -> Response:
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": temperature,
        }).encode()
        req = urllib.request.Request(
            self.URL, data=payload,
            headers={"Authorization": f"Bearer {self._key()}",
                     "Content-Type": "application/json"})

        last = None
        for attempt in range(1, self.attempts + 1):
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    d = json.loads(r.read())
                ch = d["choices"][0]
                u = d.get("usage", {}) or {}
                return Response(
                    text=ch["message"]["content"],
                    model=d.get("model", self.model),
                    prompt_tokens=int(u.get("prompt_tokens", 0)),
                    completion_tokens=int(u.get("completion_tokens", 0)),
                    latency_s=round(time.time() - t0, 2),
                    provider=self.name,
                    raw_finish_reason=ch.get("finish_reason", ""))
            except urllib.error.HTTPError as e:
                body = _redact(e.read().decode("utf-8", "replace")[:400])
                last = f"HTTP {e.code}: {body}"
                # 4xx other than rate-limit is a bad request; retrying it just
                # spends money on the same mistake.
                if 400 <= e.code < 500 and e.code != 429:
                    raise LLMError(last) from None
            except Exception as e:      # noqa: BLE001 — network faults are retryable
                last = f"{type(e).__name__}: {_redact(str(e))}"
            if attempt < self.attempts:
                wait = 2 ** attempt
                log.warning(f"attempt {attempt}/{self.attempts} failed ({last}); "
                            f"retrying in {wait}s")
                time.sleep(wait)
        raise LLMError(f"all {self.attempts} attempts failed. Last: {last}")


PROVIDERS = {"deepseek": DeepSeekProvider}


def get_provider(cfg: dict | None = None) -> LLMProvider:
    """Construct the configured provider. One place to change to swap models."""
    a = (cfg or {}).get("ado", {}) or {}
    name = a.get("provider", "deepseek")
    if name not in PROVIDERS:
        raise LLMError(f"unknown provider {name!r}; known: {sorted(PROVIDERS)}")
    return PROVIDERS[name](model=a.get("model", "deepseek-chat"))


# --- usage metering ---------------------------------------------------------

def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            at                TEXT NOT NULL,
            task_id           TEXT,
            purpose           TEXT NOT NULL,
            provider          TEXT NOT NULL,
            model             TEXT NOT NULL,
            prompt_tokens     INTEGER NOT NULL,
            completion_tokens INTEGER NOT NULL,
            cost_usd          REAL NOT NULL,
            latency_s         REAL NOT NULL,
            ok                INTEGER NOT NULL
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_task ON llm_calls(task_id)")
    conn.commit()


def record(conn, resp: Response, purpose: str, task_id: str | None,
           rates: dict, ok: bool = True) -> None:
    init(conn)
    conn.execute("""INSERT INTO llm_calls (at, task_id, purpose, provider, model,
        prompt_tokens, completion_tokens, cost_usd, latency_s, ok)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(), task_id, purpose, resp.provider,
         resp.model, resp.prompt_tokens, resp.completion_tokens,
         round(resp.cost_usd(rates), 6), resp.latency_s, 1 if ok else 0))
    conn.commit()


def usage_summary(conn) -> dict:
    init(conn)
    r = conn.execute("""SELECT COUNT(*) n, COALESCE(SUM(prompt_tokens),0) pin,
        COALESCE(SUM(completion_tokens),0) pout, COALESCE(SUM(cost_usd),0) cost
        FROM llm_calls WHERE ok=1""").fetchone()
    return {"calls": r["n"], "prompt_tokens": r["pin"],
            "completion_tokens": r["pout"], "cost_usd": round(r["cost"], 4)}
