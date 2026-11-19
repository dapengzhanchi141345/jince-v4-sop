---
name: workbuddy-local-conversations
description: Use when 读/转发 WorkBuddy 桌面端历史对话。速查本地 JSONL。
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags:
      - workbuddy
      - codebuddy
      - local-conversations
      - transcript
    related_skills:
      - session-search
---

# WorkBuddy 本地对话数据读取

## When to Use

要读、回顾、转发、提炼 WorkBuddy（CodeBuddy 桌面端）某段历史对话，或查它改过哪些文件、产出了哪些文档时。用户常说「把 WorkBuddy 的对话发过来」「看看我当时在 WorkBuddy 问了什么」。

WorkBuddy（腾讯 CodeBuddy 系桌面端）把每段对话的完整消息存在本地 JSONL，可直接读取——不需要走它的界面或 API。

## 数据在哪（按优先级找）

1. **会话消息 JSONL（唯一正文源）**：`<home>/.workbuddy/projects/<cwd-slug>/<sessionId>.jsonl`
   - cwd-slug 形如 `e-资料`（盘符-目录名）；sessionId 是 UUID。
   - 每行一个对象：`type=message`（`role=user|assistant`，`content` 是 block 数组）、`type=session-meta`、`type=tool-use` 等。
   - 旁挂子目录：`tool-results/`（工具输出）、`subagents/`（子代理 jsonl）。
2. **会话元数据**：`<home>/.workbuddy/workbuddy.db`（SQLite）`sessions` 表 = 标题/cwd/user_id/updated_at/status/model/expert_runtime_identity 等。只有元数据，**没有消息正文**——别指望它。
3. **活动会话心跳**：`<home>/.workbuddy/sessions/<pid>.json` 含 sessionId、cwd、status（定位"当前在跑哪个会话"用）。

注意本机可能有两份 `.workbuddy`：C 盘 home（`C:\Users\ASUS\.workbuddy`）与 E 盘镜像（`E:/workbuddy/workbuddy系统盘/.workbuddy`），内容同源，读任一份即可；找 projects/ 目录时两份都 grep 一遍保险。

## 提取正文的步骤

1. 定位 session：`workbuddy.db` 的 `sessions` 表按 `updated_at desc` 取最近会话；或用 `sessions/<pid>.json` 心跳拿当前活跃 sessionId。
2. 打开 `projects/<slug>/<sessionId>.jsonl`，只解析 `type==message` 的行。
3. 用户消息清洗：`content[0].text` 里裹着 `<system-reminder data-role="user-context">`（OS 信息 + SOUL.md/USER.md 身份注入）、`<user_query>`、`<cb_summary>` 等标签——**全部剥掉**才留下用户真正说的那句话。
4. 助手消息：拼接所有 `type=output_text` block；它按 step 分多行（一段对话可有数百行 assistant），汇报/转发时应合并/提炼，勿逐行倾倒。
5. 转发前检查 `identity_context` 是否被完整剥净（含 USER.md/SOUL.md 全文），群发不泄私域文件内容。

## 旁证目录（查产物/文件变更时用）

- `logs/<YYYY-MM-DD>/sdk/conversations/<sessionId>.log`：SDK 行程日志（方法调用/状态机，无正文）；
- `changes-index/`+`changes-detail/`：本会话改过哪些文件（+/- 行数、路径）；
- `artifact-index/`：PresentFiles 产物清单（含 file:// URI）；
- `file-history/<sessionId>/`：文件历史版本；
- `traces/<pid>/*.jsonl`：OTel span（只有 mcp_tools 之类 span 名，无正文，别当正文找）。

## 坑

- `workbuddy.db` 虽有 17MB 但只 11 张元数据表（sessions/automations/session_usage…），消息正文 0 条——先直接找 projects/ JSONL，别在 DB、LevelDB（`app/session/Local Storage`）、edge-sync-mapping-v4.db 里浪费时间。
- 用户消息里 `input_text` 可能带多段：第一段是 system-reminder 前缀 + user_query，剥标签后再判断是否为空（剥完为空的行是纯上下文行，跳过）。
- 会话中途额度用尽会在正文里出现「429 额度已用尽」之类的 AI 尾行，属正常记录非异常。
