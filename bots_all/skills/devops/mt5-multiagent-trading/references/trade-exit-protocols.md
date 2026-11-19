# Trade Exit Protocols (state machine + anti-whipsaw + flexible close)

How the pending-order / position state machine manages open trades. Trend and range positions use DIFFERENT exit logic — that split is the whole design.

## Per-trade lifecycle levels (L1–L6)
- **L1** position disappeared (SL/TP hit): settle P&L from `history_deals_get` by group — NEVER trust a stale in-memory last_pnl (an unrefreshed entry defaults to 0 and a winner gets mis-recorded as a loss). Loss → consec_losses+1, symbol paused ~1 day; consec ≥3 → account 24h cooldown. Win → reset consec_losses.
- **L2** adverse move, not yet at SL, structure reversing (within 0.3R of SL): early market close, don't wait for the SL slip. **TREND legs only.**
- **L3** profit ≥ 0.5R: move SL to breakeven.
- **L4** profit ≥ 1.6R: chandelier trail (peak ∓ 3×ATR), let winners run to 3-6R.
- **L5** TP hit: exit, record win.
- **L6** high-impact event within 1h: cancel pending trend orders (false-signal rate spikes).
- SL moves are one-directional only: BUY ratchets up, SELL ratchets down. Never loosen.

## Range (mean-reversion) legs: anti-whipsaw protocol
Failure mode: a Limit entry at the Bollinger boundary gets stopped out by the exact extreme it bet against (stop-hunt), always at maximum adverse excursion. Four mechanisms (mean-reversion risk literature: regime filter + statistical stop + time stop + breach exit):
1. **Statistical invalidation stop, not a tight price stop:** SL = band edge ± 2×ATR (the point where the reversion thesis is statistically false), not 1×ATR noise. This alone removes most of the stop-hunt.
2. **Breach exit:** after ≥6h holding and no TP touch, if price closes back BEYOND the entry boundary (long fell under the lower band, short rose above the upper band) → the stretch is extending, not reverting → immediate market exit, do not wait for the SL.
3. **Time stop:** 48h (12 H4 bars) without reaching the mid-band → edge decayed → exit at the small loss. Mean reversion has a shelf life.
4. **Regime gate:** do NOT post range legs when ADX(14) > 30 (strong-trend days are where reversion trades lose worst). Trend days get only the trend leg.
Range legs do NOT get L2 early-cut (that is exactly what causes the whipsaw loss); they get L3 breakeven + TP + the breach/time exits above. Never average down on a reversion trade.

## Flexible close on deep drawdown (user-mandated, re-read not reflex)
When daily total loss (realized + floating) breaches the 10% threshold, do NOT mechanically flatten everything. Per position, count falsification evidence from a fresh chart read:
  ① D1 EMA50/EMA200 flipped against the position  ② structure broken (price back beyond the 20-bar Donchian adverse extreme)  ③ drawdown > 1.5×ATR from entry  ④ chart-reader confirms an adverse confirmed pattern (double-top/head-shoulders etc.)
- **0 evidence → HOLD:** direction still correct; keep the position, move SL to the structural level (H4 EMA50 or chandelier), tighter only.
- **1 evidence → HALVE:** cut 50% (respect lot step/min; if a half-lot is impossible, degrade to HOLD and log it), keep the probe, move SL to structure.
- **≥2 evidence → CLOSE:** market-close the whole position, don't wait for SL slip; record loss, pause symbol 1 day.
Guardrail: market exits only when spread < 100 points; frozen spread → keep SL armed and retry next cycle (never naked).

## MFE trailing exit (吃第一波, 2026-11-11 深析沉淀)
实盘单「浮盈到峰值后反转吞掉」= 出在 SL/TP 之间、峰值回吐 2/3+ 才离场的模式。治法 = 峰值浮盈(MFE)跟踪砍：浮盈回吐至峰值×(1-k)（k≈0.4~0.6）即市价砍，吃第一波，再按大周期方向决定是否二单。三条纪律：
1. **MFE 先分病再治**：MFE<0（开仓即错，从未浮盈）= 出场救不了，走砍腿/方向闸/事件窗审查，别套跟踪砍；MFE>0 才进本机制。MFE 实算配方 + 配对法 + 假「零盈利」坑 → 见 `references/mt5-deal-history-read.md` §平仓配对 & MFE 归因配方。
2. **按点差族分层，不推统一 k**：实测（同分母 13 笔）大点差族（股指/金银）MFE×0.6 砍回净赚 +$9，小点差族（币/小货币对）同参数反亏 $2.5（点差小，回吐 40% 即削没肉）——k 值按族回测定，过五验（⑥净期望线）才固化进引擎。
3. **新闸/新出场假设先同分母历史试算再建**：建 kill zone/时段冻结前把该时段全部历史单跑净 P&L——净正=建闸误伤正期望（11-11 凌晨 02-07 组 +$26.6 否决实例）；砍回参数同理，先实算再谈 k。

## Re-estimation (pending orders are living, not set-and-forget)
Each 30-min cycle re-evaluates every pending order and cancels on: regime flip (trending↔ranging), D1 direction reversal against the leg, structure drift (price moved > 2.5×ATR from the trigger point — stale level), or 48h expiry. Cancelled legs are re-posted from the NEW structure on the same or next cycle. "Cancel old, re-post new" is the loop; a pending order that can't be re-derived from current data is a zombie — kill it.
