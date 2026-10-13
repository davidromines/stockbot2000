# Ideas log

External ideas the owner shares for review. Each entry: what it is, what we take,
what we do not, and why. Nothing here changes live trading. Adopted items are
tracked in the plan they attach to (currently Addendum F, Stage AB).

## 2026-10-13 #1 — "24/7 autonomous crypto trading agent" prompt (screenshot)

**What it is.** A social-media prompt for a 24/7 crypto agent: an LLM "brain" does
research and code; a fast "reflex" model (a product called Jev) scores every
candle from an order-book snapshot in ~81 ms; hard risk limits live in code; the
system rewrites its own decision schema every night; a build harness (AgentKit,
agenkit.xyz) is to be installed into Claude Code. Promotional. The products and
latency claims are unverified; no site was opened and nothing was installed.

**Does not fit this system.**
- Order-book / millisecond trading. We trade US equities on daily bars through
  market orders, and crypto is gated off with a measured ~1.9% round-trip spread,
  which kills any high-frequency edge. We have no order-book feed.
- Nightly self-rewrite and auto-ship of the live decision logic. That is the loop
  that produced this project's measurement artifacts (selection on the same data,
  1.05M-trial search, now frozen), and live changes need owner approval.
- An LLM in the live order path emitting "calibrated probabilities". No evidence
  they are calibrated; our policy keeps LLMs out of execution.
- Fractional-Kelly sizing. It needs a trustworthy edge estimate; we have none yet,
  and overestimated edge makes Kelly overbet. Stock slots stay fixed $20.
- Narrative / tokenomics "asymmetric setups". Untestable and bias-prone.

**Already how we work (confirms the design).** Hard limits in code and outside the
model (`risk_engine.py`, `killswitch.py`, `config/risk.yaml`); brain/reflex split
(research factory vs execution layer); typed signal schema (`signals.py`); "survive
over looking profitable" is the project's standing caution.

**Adopted, attached to Addendum F.**
1. **Calibration of the ranking itself** (Phase B3/F): compare each strategy's
   predicted per-20-session return with what it later realised, as reliability
   bins plus a Brier-style score, not only a mean. Parts exist
   (`degradation.py`, `live_feedback.py`, `model_calibration.py`); extend, do not
   rebuild.
2. **A mandatory "WHAT COULD BE WRONG" section** in every audit report and weekly
   digest, listing the strongest argument against the headline finding.
3. **Nightly review stays measure-only**: read fills and misses, report; never
   rewrite live logic automatically.
