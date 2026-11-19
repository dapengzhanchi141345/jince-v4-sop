Use when 金策宗师团"通过行情分析学会开单"研讨后、或新会话要接上"准头表→候选 / 时段权重→开评"两跳焊通现状。

## 背景 (2026-10-13 研讨 "学会通过行情分析开单", 用户连令 "务必把各自学习感受分享出来")
@chief 实拉两格"半焊/没接": ①方向反馈环 direction_feedback 只"刷新表"没接"提权进候选"(auto_run_cycle.py:514 半焊); ② xu_time_weight.json 有写入方(xu_oos_bridge.py:68) 0 消费方。@hermes 主持当晚两跳全焊, 0 LLM 接线活, 提权不提仓红线不松。

## 跳① 准头表→候选提权/否决 (pending_orders.py _load_intra_pool, 约95行)
- 真读 data/direction_feedback.json 的 `sym[品种].action`:
  - `veto_only` (准头<0.40 且 n≥5) → 该品种从池单剔除
  - `promote` (准头≥0.60 且 n≥5) → 排序置顶 (只改候选优先级, 手数/风险参数 0 动)
  - `insufficient` (n<5) → 不表态, 维持原样
- 用模块级 `json` 导入(不是嵌套 _json); fail-open: 准头表读不到→veto/prom 空集, 不影响主循环
- 实跑销绿证据: 构造临时池(RIOT/UNI/SOL) → 输出 `[方向闸] 提权置顶: ADAUSD,UNIUSD,XLMUSD,XTZUSD`, UNIUSD(promote, exp4.0) 压过 exp7.0 普通腿排第一 = 置顶生效

## 跳② 时段权重→开评 (jince_node.py 开评段)
- 新增 `xu_time_gate()`: 读 data/xu_time_weight.json 的 `dst_top_hours`/`dst_bottom_hours` (DST校准口径! 固定+8 的 top_hours/bottom_hours 已降级存档, dst_note 写明夏季错位1h, 勿用旧字段)
- 逻辑: 当前BJT时 ∈ dst_bottom_hours → 本时段研判降档/否决门; ∈ dst_top_hours → 正常研判; 其余中性; 只做否决门+提权参考, 不单独开仓
- 焊入 build(): ①.5 时段闸行插入 ②(我方挂单)之前; fail-open 无文件/无字段返回""
- 实跑销绿: 现22:43 BJT → 中性段(不降档不否决), 命中逻辑正确

## grep 销账口径 (供 @chief/@hermes 次日验)
- pending_orders.py 出单段 → 真读 `sym[sym]["action"]` 且走剔除/置顶分支 = 跳①焊上
- jince_node.py 开评段 → 真读 `dst_top_hours/dst_bottom_hours` = 跳②焊上

## 冲突注意 (务必知会 @strategy-rd)
- L4 池单闸 data/intra_pool_gate.json (active=True/lifted=False) 在 _load_intra_pool 入口短路 → 池单0放行(失效闸期不放水)。方向闸只改排序不放水, 两格不冲突。
- @strategy-rd 修 184/184 全正口径(exp_R 字段 bug + n_fill≥60 虚设)时, 别把这次的方向闸读法冲掉。

## 出徒倒排 (最快合规赚钱路径, 非"追样本最多")
- 优先攒 **EURJPY**(差10笔/pf2.2, 四件齐最可能过出徒线), 别追 GBPCAD(差8笔但 pf1.05 薄边, 攒满也放大不了=白攒)。EURNZD 差11/pf1.6。
- 两跳焊通 = 0.01 验证仓按"准头高的品种+赚的时段"优先挂, 样本攒得又快又对。放大仍走出徒四件齐(30笔同号+payoff≥2+强制SL+L4)。

铁律不变: 日亏10%熔断 / 连亏3笔24h冷却 / 品种日≤3单 / 提权不提仓。历史回测≠未来收益。