---
name: sensitive-action-gate
description: 敏感动作先过审查闸 gate.py。Use when 对外发送、花钱、动实盘、碰凭证、删数据、发对外物。
version: 1.0.0
author: hermes-default
metadata:
  hermes:
    category: devops
---

# 敏感动作审查闸（Grok Bot Auto Review 对应物）

## 何时触发
任何动作落在以下类别之一，执行前先跑闸：
- external_send 对外发消息（微信/邮件/IM/给客户）
- money 花钱/转账/充值/购卡
- live_trading 实盘(REAL)开平仓、魔号、账户资金、实盘手数
- credentials 读/改/转发 密码、key、卡号、2FA
- system_critical 杀非本系统进程/改注册表/改系统服务/删数据
- file_delete 删无备份文件
- publish 首次对外发布

## 命令（0 LLM 确定性）
```bash
"E:/workbuddy/国外模型/hermes/hermes-agent/venv/Scripts/python.exe" "E:/AgentCommons/shared/action_review/gate.py" check <category> --action "干什么" --detail "细节"
```
- 退出码 0=allow 直接做；10=escalate 动作挂起，iLink 发一句话请李彦明确认（15min 哨兵会自动推待批清单），他回「可以 <申请号>」后先 `gate.py approve <申请号>` 留痕再执行；11=block 不执行，给清单/建议由李本人做。
- 未定义类别一律从严 escalate。

## 文件
- 策略: E:/AgentCommons/shared/action_review/policy.json（改 policy 需李彦明点头，属 L5 域）
- 留痕: 同目录 audit.jsonl / approval_requests.json
- 哨兵: cron 24498ac4951e（15min no_agent，脚本 action_review_watch.py，静默=无待批）

## 边界
- 金策 DEMO 60137964 练习挂单走金策全授权 v4 + 练习闸，不属于本闸 live_trading 拦截（那是 REAL）。
- hermes/金策/共同体自身自愈重启 = allow，照自修复链走。（例外：从 terminal 执行 `hermes gateway restart`/一键重启网关.bat 会被终端敏感命令确认闸拦（11-15 实踩：1 分钟无回应自动 block，指令明言勿重试/勿换路）；正确路径=给李彦明两个选项：回一句「重启网关」确认由 agent 执行，或他本人双击 `E:\workbuddy\国外模型\hermes\一键重启网关.bat`（30 秒断通，交易链不受影响）。）
- 闸只留痕不改交易链；实盘红线 L5 永远李彦明确定。
