# 挂单全清场/残单撤单 SOP（用户令「把挂单撤了」类, 练习户 60137964）

## 全清场流程（11-17 实证, 35 张 GTC 挂单一次性清场）
1. 实读 `orders_get()` 全量挂单, 统计 magic 分布（先看清撤哪些）。
2. 逐张撤: `mt5.order_send({"action": getattr(mt5,'TRADE_ACTION_REMOVE',3), "order": ticket})`, `retcode==mt5.TRADE_RETCODE_DONE` 判成功, 间隔 0.15s 防终端拥塞。**撤单请求只带 order 票号**——多带 symbol/type 旧字段会 10013。
3. **每张当拍写 `data/order_lifecycle.jsonl`**（ev=cancel, op=cancel_manual, ticket+sym+magic+rc+note 原因）——撤单与台账同拍铁律, 禁「撤完再补账」; 补账=撤单不可归因。
4. sleep 1s 后实读 `orders_get()` 验证残留张数, 残留逐张点名。

## rc=10018 Market closed 残单
- 品种休市撤不动 ≠ 失败死等。处置: ①挂 one-shot 重试哨（如 2h 后查该票仍在且市场可撤即撤, 撤不动再顺延）②既有 GTC 超龄哨（如 30h 强平/超龄）作兜底, 双保险不裸奔 ③残单在位期间该品种无成交风险（市场未开）, 如实报「N 撤 1 残, 16:00 自动重试」, 不静默留残单。

## 用户手工删除残单（外部事件）
- 用户自报「我删了最后那单」后: ①实读确认 0 挂单 0 持仓 ②台账补 1 行 `op=cancel_external_user`（外部事件也必须留痕可归因: 票号+sym+magic+注「用户手工删, bot 实读验证 0」）③**暂停**为该残单登记的 one-shot 重试哨——`cronjob_manage` 无 delete 动作（报 Unknown action）, 用 `action=pause` 并留 paused_reason, 否则哨到点空跑/误报。

## 撤单脚本字段防御读
- `orders_get()` 同批结果 dict 与 TradeOrder 混杂, 且本 build TradeOrder 可缺 `.price`（11-17 AttributeError 实踩; place_sd_all dedup 亦在 dict 上取 `.magic` 崩过）→ 订单只读 `.ticket`/`.symbol`/`.magic`, 展示价格先 `getattr(o,'price',None)` 判空, 或走 `mt5.symbol_info(symbol)` 取价。撤单逻辑不依赖价格字段, 天然免疫此坑。

## 清场期纪律（参数优化窗口）
- 撤单清场=参数表过渡期（vN→vN+1）的配套动作: 清场期 0 新挂单（挂单器/补跑哨不重挂旧参数单）, 直到新参数提案前向攒样开波。1.0 手通道冻结类 L5 裁定维持, 撤单不碰 REAL 通道。
