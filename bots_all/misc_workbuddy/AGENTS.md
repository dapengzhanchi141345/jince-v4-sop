# 共同体接入（AGENTS.md）

本机有三个智能体：`workbuddy`（WorkBuddy）、`hermes`（Hermes）、`dsh`（DeepSeek Harness）。
它们共用 **`E:\AgentCommons`**：宪章 `COMMONS.md`，记忆 `memory\`，收发室 `bus\`。

## 会话开始（每个会话必做，约 10 秒）

```powershell
E:\AgentCommons\bin\commons.cmd status
E:\AgentCommons\bin\commons.cmd inbox -Agent <自己代号>
```

- 有消息 → 处理 → `ack -Id <id> -Body "<结论>"`；需要让对方知道就 `reply`。
- 没消息 → 正常干活；收尾 `note` 一行，新事实补进 `memory\facts.md`。

## 铁律

1. 先读后写：先看 `memory\facts.md`，别重复问用户已记录的事。
2. 消息必回：收件箱每条都要 `ack`，做不了也要回。
3. 单一事实源：结论只落一处（facts / decisions / journal）。

## 分工

- 文档 / PPT / Excel / 腾讯文档 / 公众号排版 → `workbuddy`
- 长链路自动化 / 量化 / 定时任务 → `hermes`
- 本机文件 / 改配置 / 写代码 / 跨应用 → `dsh`

交接必须带：**目标 + 验收标准 + 期限**。

## 给 Hermes 的快捷方式

`E:\AgentCommons\bin\relay.cmd hermes` 可无头清空收件箱并自动回复。

完整协议见 `E:\AgentCommons\COMMONS.md`；技能版见 `E:\AgentCommons\skills\agent-commons\SKILL.md`。

## 共享数据（2026-11-02 契约）
- 实盘真值唯一来源：E:\AgentCommons\shared\live_state.json（yushi 只读 attach MT5 写入，原子替换）
- 一键读：E:\AgentCommons\bin\state.cmd
- 规则：报“持仓 / 挂单 / 净值”前先跑 state.cmd；超过 30 分钟未更新 = 过期，先跑 E:\AgentCommons\yushi\bin\snapshot.cmd --shared 再引用
- 派生簿（pending_orders_state / crypto_pending_state）只作留痕，不得当口径