# Prediction ladder — 2026-10-20 (Stage AD5)

Target: excess over SPY, next open to next open. Fit 2010-2019, compared on 2020-2022; 2023+ untouched. A more complex rung is kept only if it beats the simpler one's validation IC by more than 0.005.

| h | ridge IC (t) | XGBoost IC on the same rows (t, dates) | kept |
|---:|---:|---:|---|
| 5 | +0.0412 (+3.9) | -0.0303 (-1.7, 145) | ridge |
| 20 | +0.0594 (+2.6) | -0.0562 (-1.8, 145) | ridge |
| 60 | +0.0902 (+1.9) | -0.0764 (-1.4, 145) | ridge |

Frozen models: ridge-h5-8fc10c41e3, ridge-h20-c397e26ab1, ridge-h60-4f49d6d1d1

Ridge coefficients (h = 20), on per-date ranks centred at zero:
- gross_profitability: +0.00815
- mom_12_1: +0.00473
- book_to_market: +0.00419
- low_vol_60: +0.00330
- rev_1w: +0.00309
- fcf_to_price: +0.00144
- sue: -0.00142
- neg_asset_growth: -0.00096
- sue_fresh: +0.00031
- earnings_yield: +0.00026
- mom_9_1: -0.00025
- neg_accruals: +0.00009

Forecasts are written daily to `prediction_log` (shadow); nothing trades on them. Calibration is checked with `--calibration` once horizons pass.
