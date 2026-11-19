# 机构订单流 L1 管道 · VPIN/OFI 接活 & tick 数据底座

灵魂铁律的落地层：逐笔 tick 数据 + VPIN/OFI 流动性门。接活前读本页。

## vpin_ofi 模块现状（R11 实锤，别当已接活）
`E:/GoldstrategyEngine/enhancements/vpin_ofi/`（07-14 写入后 4 个月零引用、output/ 空）。首跑（3 品种）诊断：
- 量买/卖分割用最粗代理（close>open 全量归一边）→ 另一方向全 0 → min_vol≡0 → **vpin 输出恒 0**，VPIN>0.7 禁入场闸结构上永不触发；
- `BUCKET_VOL_MULTIPLIER` 算了 `bucket_vol` 但后续从未使用（标准 VPIN 的量同步分桶根本没实现）；
- 数据源 M5 `copy_rates` 近似，OFI 出 ±2/±4 凑整假值；阈值 0.7 从未校准（模块从没出过真实输出）。
- `LiquidityGate` 三态逻辑（OPEN/REDUCED/CLOSED）本身可用，修好数据源即是现成否决门。

## 接活最小路径（5 步，验收=R11 差异证据）
1. 数据源换 `copy_ticks_range` tick 级（XAU 12h 约 36 万笔，拉取数秒）；
2. tick rule 推 Delta：close 方向 × 量（该 build tick 记录无独立 bid/ask 字段，这是标准近似，不是缺陷）；
3. 量同步分桶：每桶 = 滚动均量 × 100 ticks，把 `BUCKET_VOL_MULTIPLIER` 真正用上；
4. OFI = ΣDelta/Σ|Delta|（真实失衡分布，出非凑整值）；
5. 阈值用实测 VPIN 分位校准，不再拍 0.7。
验收（R11）：输出不再是 0/凑整值；raw≠gated 差异可复现。

## copy_ticks 使用坑（实踩）
- `copy_ticks_range` 返回 **numpy 结构化数组**：判空必须 `ticks is not None and len(ticks)>0`，裸 `if ticks` 抛 "truth value of an array is ambiguous"；
- tick 记录 = 8 字段 MQL4 风格：(time_s, open, high, low, close, time_ms, tick_volume, 末字段语义未定，XAU 上实测为 0)，字段按下标取别按名取；
- 原始 tick_volume 有封顶效应（XAU/AVGO/INTC 三品种 P50-P90 分位全 =134）→ 量能代理走 M1 K 线聚合 + 自推 Delta，勿直接用原始 tick 量分位；
- 落盘目录 `E:/GoldstrategyEngine/data/orderflow_ticks/`；可用探针 `E:/workbuddy/国外模型/hermes/scripts/orderflow_tick_probe2.py`（env -u PYTHONPATH -u PYTHONHOME + ate python 调，模块名 `MetaTrader5`）。

## deco 时段结论已证伪（R6，11-06）
deco 385 笔反事实（16/17/18/23 服务器时合计 -10,362「最大金矿」）与徐 DST 闸同分母交叉：deco 那 4 个时点按 -2h 口径落到我方 BJT 21/22/23/04 时，而 1107 交易日 × 13 万笔 DST 大样本里这四个 BJT 时**全部正净**（21 时 +9.5k、22 时 +12.1k），我方 top2 赚时是 01/18。根因假设 = deco 固定 20 美元 SL × 高波动美盘时段的交互效应（双向被扫），不是时段本身 → 其时段结论在我方口径下不成立，只作假设待 L1 tick 回验；照搬会把我方最赚时段全停掉。

## 待裁并入（rd_queue）
- `orderflow_soul_L1_liveverify_20261106`（L1 管道 + 四步流程回验）；
- `deco_session_mask_p0_20261106`（ask 含 3:1 vs 1:1 RR 口径同分母 WFO 裁决、Brooks 二次入场统计补洞、成交量方向疑点回读校准、deco 时段 R6 结论）。


## 2026-11-09 修正: tick 历史存留窗口极短, L1 管道改活体日采口径
- **实踩(11-09 周一)**: `copy_ticks_range("XAUUSD", 10-25起, now)` 全 0 行; 11-05/11-06/11-08 各起探也全 0 —— MT5 终端 tick 存留窗口极短(约 1 日内), 终端重启/换代后旧日 tick 即清。**7日滚动 tick 管道无法回补历史, 11-06 的 36万 tick 是最后的全量 tick 日(当时当班实读才拿到)**。
- **L1 管道口径改为活体日采**: 每日 21:30 jevo 当班实读当日 XAU tick(拉得到就全量, 拉不到走 M30 K 线兜底, 与币系 11-08 同款), 落盘 `data/orderflow_ticks/XAUUSD_<date>_(ticks|m30).csv` + 滚动台账 `xau_ticks_7d_rolling.json`(记每交易日 mode=tick|fallback + CVD proxy 关键小时 BJT11/15/16/18)。3-4 交易日目标按"当日实读"攒, 不再指望回补。
- **11-09 当日**: tick 0 行 -> M30 兜底 31 根(00:00-14:00 UTC, last_close 4122.4); BJT16 否决门不加新证据维持 WATCH(chop 型双扫, 11-06 双证)。
- 上方"XAU 12h 约 36 万笔, 拉取数秒"仅对**当班实读**成立, 历史日无保证。
