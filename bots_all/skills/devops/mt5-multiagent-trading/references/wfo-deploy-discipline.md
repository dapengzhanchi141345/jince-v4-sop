# WFO 部署/裁定纪律（11-13 主 bot 误部署纠正沉淀）

## 1. 裁定单一事实源 = 状态卡，效率播报只当线索
- **WFO/裁定类部署动手前必读状态卡+rd_ledger_24h 最终销账口径**。效率播报摘要（如「APPROVE_XTI_WATCH5_REJECT5」）和 `research/liquid_wfo_*_result.json` 的原始 verdict 字段都只是**线索**，不是裁定。
- 带「裁定/降级/翻闸」字样、时间更晚的销账条目，总是压过播报摘要。
- 反例（11-13 08:0x）：按播报摘要+verdict 把 AUDUSD sl/tp 1.0/4.0 写进 practice_params 双副本，撞了状态卡 06:2x 销账（AUD 已降级 WATCH 不部署、XTI 已翻闸生效）→ 回退 2.0/5.0 + 发 workbuddy 纠错件作废「XTI 口径对齐」工单。
- 同批教训：给总线下游发过「待办/对齐」件后，若上游裁定变了，**必须发纠错件引用原 MsgId**，否则下游（进化营）会照旧排工单。

## 2. WFO 翻闸两通道，优先 wfo_syms flag
- **通道①（翻闸首选）**: `E:/GoldstrategyEngine/data/l24_feature_flags.json` 的 `wfo_syms` 键（magic 门控 30261103，引擎 L24_WFO_SYMS 块 + `_struct_sl_tp` 合并消费；最小影响：12h 哨/0.01手/硬闸全保留；flag note 里写证据来源 research 文件路径）。
- **通道②（全品种基线）**: `E:/GoldstrategyEngine/data/practice_params_all_symbols.json`——**data/ 主文件（引擎权威源，live24.py:160 读它）+ fresh/ 副本要同步写**；引擎**模块导入期读参、无热读**（live24.py:223 `SYMBOLS, PER_SYMBOL = _load_symbols_live()`）= 参数改动**下次引擎自然重启才生效，别为生效强重启**（boot_guardian 会自动拉引擎，8min 启动长窗）。
- 引擎每品种只消费 `sl_mult`/`tp_mult` 两个字段；7 个信号字段（adx_min/break_margin/vol_k/min_body/h1_on/max_hold_h/giveback）归影子链/进化营，主 bot 不越线写。
- 改前备份（`.bak_wfo*`）+ 写入留溯源字段，回退时删溯源字段留 `_revert` 痕迹。

## 3. 状态卡只写已发生且验活的事实
- **禁止预写待办事件**（11-13 曾误预写「网关 11:13 已重启」被自查删）：未发生的事件写「现状+待谁执行+发生+验活后才按实补写本条目」格式，并留防复发注。

## 4. 总线原件去 processed/ 找
- 总线消息被取件哨处理后**数分钟内**即移入 `E:/AgentCommons/bus/inbox/<user>/processed/`（文件名 `YYYYMMDD-HHMMSS__from__to.json`）；读原件/补件/查回执去 processed/ 按时间戳找，别假设原件还在 inbox 根目录。
