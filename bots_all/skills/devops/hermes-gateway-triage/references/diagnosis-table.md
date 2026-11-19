# 症状 → 怀疑 → 动作 对照表

| 症状 | 第一怀疑 | 快速验证 | 动作 |
|---|---|---|---|
| 桌面发消息报 SESSION_NOT_OWNED | 死进程留的僵尸租约 | `session_turn_leases` 里 holder 的 pid 已死 | 删除死 pid 租约行 |
| 桌面正常、微信收不到 | 换网后轮询循环断掉 | gateway.log 持续 `poll error`，本机直连 443 正常 | 用户点头后重启网关 |
| 桌面微信都断 | 网关本体挂了 | `gateway_state.json` 的 pid 在 tasklist 里查无 | 跑 `hermes gateway restart`（需确认） |
| 某通道间歇断连 | 网络抖动/DNS | 直连测试时好时坏 | 不用修，轮询会自愈；持续 10 分钟仍报错才升级 |
| 微信「开通/收不到」但网关与凭证都正常 | iLink session-not-ready（bot 不能先开口） | 直探 sendmessage 回 `ret=-2 "prepare failed"`（带不带 context_token 都一样） | 用户先给微信 bot 发一条消息唤醒；不行再 QR 重登；详见 `ilink-weixin-reconnect.md` |
| 租约持有 pid 活着但会话看着没动 | 桌面 app 正常接管中 | pid 活 + 会话仍在更新 last_activity | 不动，等 expires_at |

本机关键路径（均在 `E:\workbuddy\国外模型\hermes\`）：`state.db`（会话+租约）、`gateway_state.json`、`logs/gateway.log`、`一键重启网关.bat`。
