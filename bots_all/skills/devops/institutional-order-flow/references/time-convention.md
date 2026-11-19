# 金策时间口径（李 11-15 令：汇报一律北京时间）

- **所有汇报/任务时间 = 北京时间(+08:00)**；MT5 服务器数据（UTC epoch / bar t / p.time）先 +8h 再报，标注「北京时间」
- 本机系统 = UTC+8；所有 jsonl / place_log 的 naive 时间戳 = 北京时间（无需转换）
- 全部金策 cron 任务 timezone=Asia/Shanghai。SD 批现行：
  - `92212bf4d61e` 12h/24h 分级强平哨（每 30min，脚本 sd_forceclose_cron.py）
  - `afe459d823a0` 周一 **21:15** 全品种挂单首波（30 品种，脚本 sd_place_fx_monday.py；原 21:05 与 jince-node 美盘开评同秒抢 MT5 IPC，已错峰）
  - `02d625d6de0a` 周一 **22:40** 二道波（重跑同脚本：dedup 自动跳已挂，只补 10015/10018 败单品种，美股 22:30 开市后落）
- 周末 tick.time = 停更旧时间戳（不是服务器时钟错）；持仓 p.time = 开仓时服务器 Unix 时钟，强平 12h/24h 差值周一开仓后正常
- Windows 计划任务 SD-ProfitLock 无时区概念（AtStartup + 1min 心跳，唯一锁）
