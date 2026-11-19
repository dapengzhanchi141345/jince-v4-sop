# 离场/锁利规则回测纪律（保本 / 追踪 / 分批 = 风控层，非 edge）

When a proposal changes HOW a position is exited or managed — move-to-breakeven at kR, trailing stop, partial take-profit, time-exit — instead of WHEN it is entered, treat it as a RISK-LAYER rule. Distinguish from `references/trade-exit-protocols.md` (exit *execution* mechanism: anti-whipsaw, L1–L6 loss state machine) and `references/leg-polish-five-test.md` (entry *signal* 5-test). This file is the *validation/gating* method for an exit rule.

## 1. 先核 R 口径 (verify the R unit before trusting any EV number)
- "R" must be a risk-multiple, not a raw ATR-multiple. If a report cites "R", check: true R = (ATR-multiple) / SL-multiple. A report that labels ATR-multiple as "R" overstates absolute EV by roughly the SL-multiple (~3×); direction can survive, magnitude is wrong. Re-derive every "R" figure before citing it to a gate.
- Same denominator: re-score ALL candidate exit rules on the identical event set (same signals, same SL/TP geometry, spread deducted). No per-rule resampling.

## 2. MFE 口径分上/下界 (an exit rule's EV gain is model-dependent — the sign can flip)
- Live = tick polling (~20s) → sees intra-bar spikes = UPPER bound on maximum favorable excursion (MFE).
- Offline M15-close backtest = LOWER bound (misses intra-bar spikes) but byte-reproducible.
- A "raises expected value" claim often lives ENTIRELY in the MFE basis: the tick basis says +EV, the M15-close basis says −EV. Only grant conclusions BOTH bases agree on. The conclusions usually both agree on: (a) pure trailing HURTS EV; (b) breakeven raises win-rate and lowers per-trade std-dev (trades a little EV for stability).
- Rule: if only one basis shows a gain, do NOT market the gain. The conservative, byte-reproducible basis is the only one a customer/reviewer can actually verify.

## 3. 高胜率 ≠ 正期望 (mirror) — risk-layer, not edge
- A breakeven/trailing that lowers EV but raises win-rate / lowers drawdown / limits giveback is a RISK-LAYER tool. Grant it "risk-layer permission" only: never as an edge, never into the 30-trade OOS 出徒 / 五验 pipeline, never as a "多赚 / 期望翻倍" claim.

## 4. 肥尾前置检查 (fat-tail precondition for "early breakeven is free")
- You may only claim "move to breakeven early is free" when TP is capped so there is NO long right tail. TP-cap in R = TP_MULT / SL_MULT. If the strategy can run an 8R+ winner, an early breakeven locks you out of it and is NOT free. Compute the TP cap and confirm no fat tail before recommending an early-be threshold.

## 5. 撤闸杆挂风控指标，不挂 EV (kill-switch ruler)
- A risk-layer permission's degradation tripwire must monitor the RISK objective it was granted for: 浮盈回吐率 (fraction of +≥kR trades that end ≤0), 最大回撤, 保本局"名义保本实亏"次数 — measured against the fixed baseline. Do NOT gate on "per-trade EV < fixed EV": the conservative basis already predicts the risk rule < fixed EV, so an EV-ruler kill-switch is pre-destined to trip and kills the very benefit you granted.

## 6. 只收紧不放松 + 缓冲盖住点差 (tighten-only; buffer covers live spread)
- Exit management may move SL only in the favorable direction (never loosen it back).
- Breakeven buffer must cover the live spread; a fixed buffer smaller than current spread makes a "breakeven" exit still net a loss. Use ≈1.5× the current spread, not a hardcoded constant.

## 7. 通电终钮分离 (arming vs. trading are different gates)
- Arming an exit rule (guard --live) and reviving the underlying trading leg are SEPARATE gates. A leg can be RETIRED / frozen with 0 holdings while the exit rule is "policy pre-authorized but not powered." State which gate is open before claiming the rule is "in effect," and never bundle "arm the rule" with "gold orders resume".

## 8. 落盘留痕 (a reproducible baseline is a precondition to sign)
- The raw backtest output must be archived to `data/` (byte-stable, self-labelled as the conservative M15-close basis) before a risk-officer signs --live. Numbers living only in code comments are not auditable; a live risk action needs a checkable data file + fields, not comment prose.
