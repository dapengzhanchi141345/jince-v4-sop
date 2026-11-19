# 闸翻位与执法层同步（L4 解冻操作流 + 「全部放开」三件同步）

## L4 解冻裁定操作流（用户令「全部解冻」后走此流，实测）
用户令=最高优先，排风控官裁定卡（kanban ready+高优，卡内写全裁定点+不动清单）；L4 复签后**三源同步翻位=真解冻**：① `data/crypto_freeze_gate.json` active→false（+l4_adjudication=UNFREEZE+ticket）② `data/risk_state.json` coin_freeze.active→false ③ `veto_log.jsonl` UNFREEZE 行（五源交叉：+rd_decisions+卡 comment）——**以三源实读为准，哨兵轮询旗标只作占位不作放行**。**L4 cap 真写位=`data/l4_consec_bridge.json`**——risk_state.json 里那份是循环每 30min 重写的派生快照，直接改会被冲掉（改错位=白改）。0.01 观察腿口径（L4 裁定）：最小手数免事件降档+12h 必平不过夜+日≤3 单照旧+30 笔同分母复测 L4 再裁；红线（retire_freeze 0 生成 0 放大/10% 熔断/连亏 3 笔）解冻不动——**解冻≠复活退役腿**。

## 数据层翻 ≠ 执法层翻（11-17 实踩）
- 闸文件 active→false 只对「每 tick 活读闸文件的执法 actor」即刻生效（pending 冻结桥每轮重读=真放行）；**缓存读源 actor（带内存态或周期重载的 closer/巡检器）不跟翻**。
- 用户令「全部放开/翻全部闸」后必做三件同步：① 落 L5 指令文件进 data/（l5_directive_*.json，列放开点+不动清单）② 总线 inbox 投递执法岗（如 risk-officer）③ 验收=下一拍执法日志引用该指令+确认不再撤单；验收前再被撤=升级报告，不默认已同步。
- 验收不可省：「翻了 JSON」≠完成——执法层不是被动数据消费者，它有独立读源/缓存，翻完不验=留一个会按旧闸继续执法的活体。