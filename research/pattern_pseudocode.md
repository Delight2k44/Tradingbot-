# Pattern Entry Engine — Pseudocode (LONG-only, MTF)
# ===================================================
# Timeframes: H1 (primary, arms zones) + M15 (trigger/refinement)
#
# HONEST FLAGS (placeholders I did NOT invent — need your numbers):
#  1. Demand zones A/B/C  -> prices NOT provided. Test uses auto-derived
#     swing-low zones. YOUR zones must be supplied for live use.
#  2. "10 points" unit    -> taken as symbol POINT * 10 (gold: 0.10 of price).
#  3. "stop wider than [x] ATR" -> rejection threshold defaulted to 3.0 ATR.
#  4. "[x]% risk"         -> defaulted to 1% (consistent with project risk).
#  5. "[n] entries/zone"  -> 1 (per spec "Max entries per zone: 1").
#  6. Cap / concurrency   -> 1 concurrent position, 1 trade/zone touch.
#  7. "spread > [x]"      -> defaulted to no-skip (measured on live).

FUNCTION evaluate_setup(closed_15m, closed_1h, zones):
    # ---------- ZONE state ----------
    for zone in zones:
        IF during_previous_recheck: state.armed[zone] = (body_midpoint crossed INTO zone)
        RE-ARM only on fresh touch from above (close was above zone, then enters)

    # ---------- DEDUPLICATION ----------
    # A 15m candle whose time window is inside the paused 1h candle + same zone
    #   = ONE setup. Entry once: timing = 15m trigger, stop from 1h low.

    # ---------- PATTERN MATCH ----------
    IF match_L1..L4(closed_1h) AND body_mid(closed_1h) inside armed zone:
        full_size = TRUE                  # 1h primary signal
        sl_price  = low(closed_1h) - 10 * POINT

    ELIF match_L1..L4(closed_15m) AND body_mid(closed_15m) inside armed zone:
        IF 1h context exists (zone armed on 1h):   # confirmed demand
            size = full; timing = 15m trigger
            sl_price = low(closed_1h) - 10 * POINT     # 1h low anchors stop
        ELSE:
            size = HALF; sl_price = low(closed_15m) - 10 * POINT

    # ---------- CONFIRMATIONS ----------
    IF close(1h_latest) < 1h_50_EMA:         SKIP   # weak 1h trend
    IF first candle after session gap:        SKIP
    IF live_spread > threshold:               SKIP
    IF (entry - sl_price) > 3.0 * ATR(14, H1): SKIP   # stop too wide

    # ---------- SIZING ----------
    lots = (equity * risk_pct) / (entry - sl_price)     # never fixed-lot

    RETURN order(LONG, lots, entry, sl_price, tp1=1.0R, tp2=2.0R)