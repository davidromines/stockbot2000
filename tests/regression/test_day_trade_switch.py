"""account_rules.check_buy: the day-trade guard obeys the operator's switch (owner, 2026-10-14)."""
import runtime  # noqa: F401
import yaml
import account_rules as ar

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

pf = {"equity": 84.0, "buying_power": 50.0, "day_trades_5d": 3, "unsettled_proceeds": 0.0}
base = {"account_type": "limited_margin", "limited_margin_settled_funds": False}
a, why = ar.check_buy(pf, base, 20.0)
check("key absent: the old guard still refuses the 4th day trade", a == 0.0 and why and "day trades" in why)
a, why = ar.check_buy(pf, {**base, "enforce_day_trade_limit": True}, 20.0)
check("switch true: refuses", a == 0.0 and why is not None)
a, why = ar.check_buy(pf, {**base, "enforce_day_trade_limit": False}, 20.0)
check("switch false: the buy is allowed", a == 20.0 and why is None)
a, why = ar.check_buy({**pf, "day_trades_5d": None}, {**base, "enforce_day_trade_limit": False}, 20.0)
check("switch false: an unknown day-trade count no longer blocks", a == 20.0 and why is None)
a, why = ar.check_buy({"equity": 84.0, "buying_power": 50.0, "unsettled_proceeds": 45.0},
                      {"account_type": "cash", "enforce_day_trade_limit": False}, 20.0)
check("a cash account's settled-funds rule is untouched by the switch", a == 5.0)
lim = yaml.safe_load(open("config/risk.yaml"))
check("production risk.yaml has the switch off", lim.get("enforce_day_trade_limit") is False)
check("other risk limits are untouched", lim["max_daily_loss_dollars"] == 15.0 and lim["max_drawdown_percent"] == 35.0 and lim["max_open_positions"] == 5)
print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
