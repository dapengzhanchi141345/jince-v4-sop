---
name: meeting-minutes
description: 会议录音/录像转纪要+行动项。Use when 李彦明丢来会议录音录像文件或要复盘一场会。
version: 1.0.0
author: hermes-default
metadata:
  hermes:
    category: productivity
---

# 会议记录 → 纪要 + 行动项

## When to use
- 李彦明发来会议录音/录像（.mp3/.mp4/.mov 等）或说「把这场会总结一下」。
- 金策群内出现「特别会议」「讨论一下」后需要出纪要。

## 流程
1. **取文字**（三选一，按可用性）：
   - 录像/带音轨：`video_analyze`（多模态）或先抽音轨（`E:/workbuddy/国外模型/hermes/tools/ffmpeg-9.0.1-win32-x64/bin/ffmpeg.exe -i in.mp4 out.wav`）再走本地 whisper（`faster-whisper` 已装进 hermes venv，模型 base 已缓存；中文要更准可换 small，HF 走 `HF_ENDPOINT=https://hf-mirror.com` 下载）。
   - 纯文本纪要草稿/会议链接文字：直接读。
2. **出纪要**（固定四段，大白话）：
   - 会议主题与时间
   - 结论（谁定了什么，一句话一条）
   - 行动项表：事项 / 负责人 / 期限 / 验收标准（四列，缺一样打回）
   - 待再议（没定下来的）
3. **落盘**：`E:\workbuddy\内容中心\交付\会议纪要_<主题>_<YYYYMMDD>.md`；涉及金策的结论同步写金策状态卡对应节。
4. 行动项里有 bot 能接的（排期/提醒/跟进），当场建 cronjob 或写 task_ledger，不留无主行动项。

## 边界
- Google Meet 实时入会插件在 Windows 上无效（音频桥不测）；要实时旁听会议需 Linux 机器，本机只做「会后录音转纪要」。
- 纪要只写说过的，不编；没听清的原话标 `[听不清]`。
